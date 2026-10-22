#!/usr/bin/env python3
"""Real loopback TCP/TLS plus filtering, persistence and queue-pressure tests."""
import importlib.util
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('syslog_impl', Path(__file__).resolve().parents[1] / 'usr/local/lib/consolepi_syslog.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def event(priority=6, tag='consolepi', msg='OPEN user=console client=192.0.2.1 ssh_port=2201'):
    return {'PRIORITY': str(priority), 'SYSLOG_IDENTIFIER': tag, 'MESSAGE': msg,
            '__REALTIME_TIMESTAMP': '1750000000000000', '_HOSTNAME': 'consolepi'}


class SyslogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.patches = [patch.object(m, 'ROOT', self.root / 'state'),
                        patch.object(m, 'DB', self.root / 'state/queue.sqlite3'),
                        patch.object(m, 'CONFIG', self.root / 'syslog.json')]
        for p in self.patches:
            p.start()
        self.cfg = m.validate({'enabled': True, 'host': 'localhost'})

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def test_all_thresholds(self):
        for threshold in range(8):
            for severity in range(8):
                self.assertEqual(m.choose_event(event(severity), threshold) is not None,
                                 severity <= threshold)

    def test_selection_and_secret_exclusion(self):
        self.assertIsNone(m.choose_event(event(tag='picocom', msg='password=secret'), 7))
        self.assertIsNone(m.choose_event(event(tag='consolepi-transcript-writer'), 7))
        self.assertIsNone(m.choose_event(event(tag='kernel', msg='ordinary kernel message'), 7))
        self.assertIsNotNone(m.choose_event(event(4, 'kernel', 'nft-input-drop SRC=192.0.2.1'), 4))
        self.assertIsNotNone(m.choose_event(event(3, 'systemd', 'consolepi-web.service: Failed'), 4))
        self.assertIsNone(m.choose_event(event(3, 'systemd', 'other.service: Failed'), 4))

    def test_failed_ssh_promoted_to_warning(self):
        self.assertEqual(m.choose_event(event(6, 'sshd', 'Failed password for invalid user x'), 4)[0], 4)
        self.assertIsNone(m.choose_event(event(6, 'sshd', 'Accepted publickey for console'), 4))

    def test_input_validation(self):
        for changes in [{'host':'x\nconfig'}, {'host':'https://example.com'}, {'port':0},
                        {'severity':8}, {'transport':'udp'}, {'host':''},
                        {'ca_pem':'-----BEGIN PRIVATE KEY-----'}, {'ca_pem':'bad certificate'}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                m.validate(dict(self.cfg, **changes))
        self.assertEqual(m.validate(dict(self.cfg, host='2001:db8::1'))['host'], '2001:db8::1')

    def test_octet_counting_unicode_and_sanitization(self):
        e = event(msg='Událost\n<0>injection')
        data = m.frame(e, m.choose_event(e, 6))
        count, payload = data.split(b' ', 1)
        self.assertEqual(int(count), len(payload))
        self.assertTrue(payload.startswith(b'<86>1 '))
        self.assertNotIn(b'\n', payload)

    def test_bounded_persistent_queue_and_cursor(self):
        con = m.connect_db()
        with patch.object(m, 'MAX_QUEUE', 3):
            for n in range(5):
                e = dict(event(msg=str(n)), __CURSOR='cursor'+str(n))
                m.enqueue(con, e, self.cfg)
        con.close()
        con = m.connect_db()
        self.assertEqual(con.execute('SELECT count(*) FROM messages').fetchone()[0], 3)
        self.assertEqual(m.meta(con, 'dropped'), '2')
        self.assertEqual(m.meta(con, 'cursor'), 'cursor4')
        self.assertTrue(con.execute('SELECT frame FROM messages ORDER BY id LIMIT 1').fetchone()[0].endswith(b'2'))
        self.assertEqual(m.DB.stat().st_mode & 0o777, 0o600)
        con.close()

    def test_filter_does_not_enqueue_but_advances_cursor(self):
        con = m.connect_db()
        m.enqueue(con, dict(event(7), __CURSOR='c'), self.cfg)
        self.assertEqual(con.execute('SELECT count(*) FROM messages').fetchone()[0], 0)
        self.assertEqual(m.meta(con, 'cursor'), 'c')
        con.close()

    def test_configuration_change_and_reset_purge_queue(self):
        con = m.connect_db()
        m.enqueue(con, event(), self.cfg)
        con.close()
        with patch.object(m.subprocess, 'run') as run:
            m._control('configure', self.cfg)
            self.assertEqual(m.load(), self.cfg)
            self.assertEqual(m.CONFIG.stat().st_mode & 0o777, 0o600)
            m._control('reset')
            self.assertEqual(m.load(), m.DEFAULTS)
            self.assertIn(['systemctl', 'disable', m.SERVICE], [call.args[0] for call in run.call_args_list])
        con = m.connect_db()
        self.assertEqual(con.execute('SELECT count(*) FROM messages').fetchone()[0], 0)
        con.close()

    def test_invalid_config_has_no_side_effects(self):
        with patch.object(m.subprocess, 'run') as run, self.assertRaises(ValueError):
            m._control('configure', dict(self.cfg, host='bad;command'))
        run.assert_not_called()
        self.assertFalse(m.CONFIG.exists())

    def test_activation_failure_restores_previous_config(self):
        import json
        old = dict(m.DEFAULTS)
        m.CONFIG.write_text(json.dumps(old))
        def fail_once(args, **kwargs):
            if args[:3] == ['systemctl','enable','--now']:
                raise subprocess.CalledProcessError(1, args)
            return None
        with patch.object(m.subprocess, 'run', side_effect=fail_once) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                m._control('configure', self.cfg)
            self.assertEqual(m.load(), old)
            self.assertIn(['systemctl','disable','--now',m.SERVICE], [call.args[0] for call in run.call_args_list])

    def receiver(self, context=None):
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        listener.settimeout(5)
        received = []
        def receive():
            try:
                conn, _ = listener.accept()
                with conn:
                    if context:
                        conn = context.wrap_socket(conn, server_side=True)
                    with conn:
                        received.append(conn.recv(8192))
            except (ssl.SSLError, OSError):
                pass
            finally:
                listener.close()
        thread = threading.Thread(target=receive)
        thread.start()
        return listener.getsockname()[1], received, thread

    def test_real_tcp_delivery(self):
        port, received, thread = self.receiver()
        data = m.frame(event(), m.choose_event(event(), 6))
        m.transmit(dict(self.cfg, host='127.0.0.1', port=port, transport='tcp'), data)
        thread.join(6)
        self.assertEqual(received, [data])

    def certificate(self):
        cert, key = self.root/'cert.pem', self.root/'key.pem'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1',
                        '-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost',
                        '-keyout',str(key),'-out',str(cert)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert, key)
        return cert.read_text(), ctx

    def test_tls_trusted(self):
        ca, ctx = self.certificate()
        port, received, thread = self.receiver(ctx)
        m.transmit(dict(self.cfg, port=port, ca_pem=ca), b'3 abc')
        thread.join(6)
        self.assertEqual(received, [b'3 abc'])

    def test_tls_rejects_untrusted_and_wrong_name(self):
        ca, ctx = self.certificate()
        for changes in [{'ca_pem':''}, {'ca_pem':ca,'host':'127.0.0.1'}]:
            port, _, thread = self.receiver(ctx)
            with self.assertRaises(ssl.SSLCertVerificationError):
                m.transmit(dict(self.cfg, port=port, **changes), b'3 abc')
            thread.join(6)

    def test_failed_send_keeps_message_then_recovers(self):
        con = m.connect_db()
        m.enqueue(con, event(), self.cfg)
        con.close()
        stop = threading.Event()
        def unavailable(*args):
            stop.set()
            raise ConnectionRefusedError('test offline')
        with patch.object(m, 'transmit', side_effect=unavailable):
            m.sender(self.cfg, stop)
        con = m.connect_db()
        self.assertEqual(con.execute('SELECT count(*) FROM messages').fetchone()[0], 1)
        self.assertEqual(m.meta(con, 'state'), 'retrying')
        con.close()
        stop.clear()
        def recovered(*args):
            stop.set()
        with patch.object(m, 'transmit', side_effect=recovered):
            m.sender(self.cfg, stop)
        con = m.connect_db()
        self.assertEqual(con.execute('SELECT count(*) FROM messages').fetchone()[0], 0)
        self.assertEqual(m.meta(con, 'state'), 'sent')
        con.close()


if __name__ == '__main__':
    unittest.main()
