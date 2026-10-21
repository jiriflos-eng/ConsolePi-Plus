#!/usr/bin/env python3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
from syslog_web_behavior import web
import ping_monitor as m

class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'monitor.sqlite3'
        self.dbpatch=patch.object(m,'DB_PATH',self.path);self.dbpatch.start();m.migrate()
        self.gate=patch.object(web,'firstboot_status',return_value={'pending':False});self.gate.start()
        self.client=web.APP.test_client()
    def tearDown(self):
        self.gate.stop();self.dbpatch.stop();self.temp.cleanup()
    def auth(self):
        with self.client.session_transaction() as s:s.update(authenticated=True,csrf='token')
    def call(self,path,data,method='post',token='token'):
        return getattr(self.client,method)('/ping/api/'+path,json=data,headers={'X-CSRF-Token':token},base_url='https://localhost')
    def test_auth_and_csrf(self):
        self.assertEqual(self.client.get('/ping/api/overview').status_code,302)
        self.auth()
        for token in ('','bad'):
            self.assertEqual(self.call('settings',{'enabled':True},token=token).status_code,403)
        self.assertEqual(self.call('settings',{'enabled':'false'}).status_code,400)
        self.assertTrue(self.call('settings',{'enabled':True}).json['enabled'])
    def test_crud_and_api(self):
        self.auth();response=self.call('devices',dict(name='<Router>',address='::1'));self.assertEqual(response.status_code,200)
        id=response.json['id']
        self.assertEqual(self.call('devices/'+str(id),{'paused':1}).status_code,200)
        result=self.client.get('/ping/api/overview',base_url='https://localhost').json
        self.assertEqual(result['counts']['PAUSED'],1)
        self.assertEqual(self.call('devices/'+str(id),{},'delete').status_code,200)
    def test_csv_rollback_and_period_validation(self):
        import io
        self.auth()
        response=self.client.post('/ping/api/csv',data={'csrf':'token','file':(io.BytesIO(b'name,address\nOne,127.0.0.1\nBad,;id\n'),'test.csv')},base_url='https://localhost')
        self.assertEqual(response.status_code,400)
        with m.database() as db:self.assertEqual(db.execute('SELECT count(*) FROM devices').fetchone()[0],0)
        self.assertEqual(self.client.get('/ping/api/history/1?period=nan',base_url='https://localhost').status_code,400)
    def test_public_monitor_only_when_enabled_and_projection(self):
        response=self.client.get('/ping/public/summary',base_url='https://localhost')
        self.assertEqual(response.status_code,200)
        self.assertFalse(response.json['enabled'])
        self.assertEqual(self.client.get('/ping/view/1',base_url='https://localhost').status_code,404)
        with m.database() as db:
            id=m.save_device(db,dict(name='Public router',address='192.0.2.1',description='Private configuration'))
            db.execute("UPDATE config SET value='true' WHERE key='enabled'")
        response=self.client.get('/ping/public/summary',base_url='https://localhost')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['devices'][0]['name'],'Public router')
        self.assertNotIn('192.0.2.1',response.text)
        self.assertNotIn('Private configuration',response.text)
        self.assertNotIn('down_after',response.text)
        self.assertIn('no-store',response.headers['Cache-Control'])
        self.assertEqual(self.client.get('/ping/public/history/'+str(id),base_url='https://localhost').status_code,200)
        with patch.object(web,'update_status',return_value={}),patch.object(web,'brand_identity',return_value={'display_name':'ConsolePi+'}):
            detail=self.client.get('/ping/view/'+str(id),base_url='https://localhost')
            self.assertEqual(detail.status_code,200)
            self.assertIn('data-pd-latency',detail.text)
        self.assertEqual(self.call('devices/'+str(id),{'name':'Hacked'}).status_code,302)
        self.assertEqual(self.client.post('/ping/public/summary').status_code,405)
        with m.database() as db:db.execute("UPDATE config SET value='false' WHERE key='enabled'")
        self.assertEqual(self.client.get('/ping/public/history/'+str(id),base_url='https://localhost').status_code,404)

    def test_history_bucket_budget(self):
        with m.database() as db:
            id=m.save_device(db,dict(name='Router',address='::1'))
            db.execute("UPDATE config SET value='true' WHERE key='enabled'")
        path='/ping/public/history/'+str(id)+'?period=172800&buckets='
        for invalid in ['0','1001','nan','1.5']:
            self.assertEqual(self.client.get(path+invalid,base_url='https://localhost').status_code,400)
        response=self.client.get(path+'24',base_url='https://localhost')
        self.assertEqual(response.status_code,200)
        self.assertGreaterEqual(response.json['bucket_size'],7200)

    def test_configuration_list_requires_auth_and_omits_history(self):
        self.assertEqual(self.client.get('/ping/api/devices').status_code,302)
        self.auth()
        with m.database() as db:m.save_device(db,dict(name='Switch',address='::1',interval=30))
        response=self.client.get('/ping/api/devices',base_url='https://localhost')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['devices'][0]['address'],'::1')
        self.assertEqual(response.json['devices'][0]['interval'],30)
        self.assertNotIn('stats',response.json['devices'][0])
        self.assertNotIn('last_ts',response.json['devices'][0])

    def test_template_and_local_assets(self):
        self.auth()
        with patch.object(web,'update_status',return_value={}),patch.object(web,'brand_identity',return_value={'display_name':'ConsolePi+'}):
            response=self.client.get('/ping',base_url='https://localhost')
            self.assertEqual(response.status_code,200)
            self.assertIn('role="switch"',response.text)
            self.assertIn('/static/ping.js',response.text)
            self.assertIn('nastavení zařízení',response.text)
            self.assertNotIn('id="ping-charts"',response.text)
            self.assertNotIn('id="ping-incidents"',response.text)
            self.assertNotIn('id="ping-period"',response.text)
            self.assertIn('no-store',response.headers['Cache-Control'])

if __name__=='__main__':unittest.main()
