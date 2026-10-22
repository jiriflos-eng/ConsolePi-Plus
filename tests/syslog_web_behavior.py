#!/usr/bin/env python3
"""Requires Flask/cryptography (already installed on the target appliance)."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

source = Path(__file__).resolve().parents[1] / 'opt/consolepi-web/app.py'
read = Path.read_text
with patch.object(Path, 'read_text', lambda p,*a,**kw: 'qa-secret' if str(p)=='/etc/consolepi/web.secret' else read(p,*a,**kw)):
    spec = importlib.util.spec_from_file_location('web_impl', source)
    web = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(web)
web.APP.template_folder = str(source.parent/'templates')
web.APP.static_folder = str(source.parent/'static')
web.APP.config['TESTING'] = True


class WebTests(unittest.TestCase):
    def setUp(self):
        self.gate = patch.object(web, 'firstboot_status', return_value={'pending': False})
        self.gate.start()
        self.client = web.APP.test_client()

    def tearDown(self):
        self.gate.stop()

    def authenticate(self):
        with self.client.session_transaction() as session:
            session['authenticated'] = True
            session['csrf'] = 'qa-token'

    def test_authentication_required(self):
        with patch.object(web, 'command') as cmd:
            result = self.client.post('/system/syslog', data={'action':'test'}, base_url='https://localhost')
            self.assertEqual(result.status_code, 302)
            self.assertTrue(result.location.endswith('/login'))
            cmd.assert_not_called()

    def test_missing_and_wrong_csrf_rejected(self):
        self.authenticate()
        with patch.object(web, 'command') as cmd:
            for data in [{}, {'csrf':'wrong'}]:
                self.assertEqual(self.client.post('/system/syslog', data=data, base_url='https://localhost').status_code, 403)
            cmd.assert_not_called()

    def test_config_payload_and_action_allowlist(self):
        self.authenticate()
        with patch.object(web, 'command', return_value=SimpleNamespace(returncode=0,stdout='{"message":"OK"}',stderr='')) as cmd:
            data={'csrf':'qa-token','action':'configure','enabled':'on','host':'syslog.example.test',
                  'port':'6514','transport':'tls','severity':'4','ca_pem':''}
            self.assertEqual(self.client.post('/system/syslog', data=data, base_url='https://localhost').status_code, 302)
            self.assertEqual(cmd.call_args.args[-2:], ('syslog','configure'))
            payload = json.loads(cmd.call_args.kwargs['input_text'])
            self.assertEqual(payload['severity'], '4')
            self.assertIs(payload['enabled'], True)
            cmd.reset_mock()
            result=self.client.post('/system/syslog', data={'csrf':'qa-token','action':'reset'}, base_url='https://localhost')
            self.assertEqual(result.status_code, 400)
            cmd.assert_not_called()

    def test_test_message_has_no_untrusted_payload(self):
        self.authenticate()
        with patch.object(web, 'command', return_value=SimpleNamespace(returncode=0,stdout='{"message":"Test"}',stderr='')) as cmd:
            self.client.post('/system/syslog', data={'csrf':'qa-token','action':'test','message':'SECRET'}, base_url='https://localhost')
            self.assertEqual(cmd.call_args.args[-2:], ('syslog','test'))
            self.assertIsNone(cmd.call_args.kwargs['input_text'])

    def test_web_audit_trusts_proxy_only_on_loopback(self):
        with web.APP.test_request_context('/', environ_base={'REMOTE_ADDR':'127.0.0.1'}, headers={'X-Real-IP':'192.0.2.8'}), patch.object(web,'command') as cmd:
            web.web_audit('WEB_LOGIN_FAILURE','warning')
            self.assertEqual(cmd.call_args.args[-1], 'WEB_LOGIN_FAILURE client=192.0.2.8')
        with web.APP.test_request_context('/', environ_base={'REMOTE_ADDR':'192.0.2.10'}, headers={'X-Real-IP':'192.0.2.8'}), patch.object(web,'command') as cmd:
            web.web_audit('WEB_LOGIN_SUCCESS')
            self.assertEqual(cmd.call_args.args[-1], 'WEB_LOGIN_SUCCESS client=192.0.2.10')

    def test_templates_compile_and_syslog_panel_escapes_values(self):
        self.assertIn("system.html", web.APP.jinja_env.list_templates())
        for template in web.APP.jinja_env.list_templates():
            web.APP.jinja_env.get_template(template)
        system = (source.parent/'templates/system.html').read_text()
        start=system.index('<section class="system-card">', system.index('data-system-section="logs"'))
        panel=system[start:system.index('</section>',start)+len('</section>')]
        with web.APP.test_request_context('/'):
            html=web.APP.jinja_env.from_string(panel).render(csrf='qa-token',syslog={
                'enabled':True,'host':'<script>alert(1)</script>','port':6514,'transport':'tls',
                'severity':4,'ca_pem':'','levels':['Emergency','Alert','Critical','Error','Warning','Notice','Informational','Debug'],
                'state':'idle','running':True,'pending':0,'dropped':0,'last_sent':'','error':''})
            self.assertIn('&lt;script&gt;',html)
            self.assertIn('value="4" selected',html)
            self.assertNotIn('<script>alert',html)


if __name__ == '__main__':
    unittest.main()
