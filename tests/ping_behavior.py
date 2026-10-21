#!/usr/bin/env python3
import sys
import tempfile
import time
import unittest
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'opt/consolepi-web'))
import ping_monitor as m


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'monitor.sqlite3'
        self.patcher=patch.object(m,'DB_PATH',self.path);self.patcher.start()
        m.migrate();self.now=int(time.time()//86400)*86400+10
        with m.database() as db:
            self.id=m.save_device(db,dict(name='Router',address='192.0.2.1'))
    def tearDown(self):
        self.patcher.stop();self.temp.cleanup()
    def record(self,values):
        with m.database() as db:m.record(db,self.id,values)
    def test_peak_preservation_and_retention(self):
        times=[self.now+i for i in range(5)]
        self.record([(t,'ok',v,'') for t,v in zip(times,[8,9,10,450,12])])
        with m.database() as db:
            result=m.history(db,self.id,self.now-1,self.now+10,limit=1)
            self.assertIn((times[3],450),[p for b in result['buckets'] for p in b['points']])
            for resolution,_ in m.RESOLUTIONS:
                row=db.execute('SELECT * FROM aggregates WHERE resolution=?',(resolution,)).fetchone()
                self.assertEqual((row['max_rtt'],row['max_ts']),(450,times[3]))
            m.cleanup(db,self.now+8*86400)
            self.assertEqual(db.execute('SELECT count(*) FROM samples').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT max(max_rtt) FROM aggregates').fetchone()[0],450)
            with patch.object(m.time,'time',return_value=self.now+8*86400):
                archived=m.history(db,self.id,self.now-1,self.now+10,limit=1)
            self.assertIn((times[3],450),[p for b in archived['buckets'] for p in b['points']])
    def test_multiple_peaks_loss_and_unknown(self):
        self.record([(self.now+i,'ok',v,'') for i,v in enumerate([8,450,10,700,12])]+[(self.now+6,'timeout',None,''),(self.now+7,'dns',None,'')])
        with m.database() as db:
            a=db.execute('SELECT * FROM aggregates WHERE resolution=60').fetchone()
            self.assertEqual((a['attempts'],a['successes'],a['losses'],a['unknowns']),(6,5,1,1))
            self.assertEqual(a['max_rtt'],700)
            self.assertEqual(db.execute('SELECT count(*) FROM peaks').fetchone()[0],2)
            self.assertIsNone(db.execute("SELECT rtt FROM samples WHERE outcome='timeout'").fetchone()[0])
    def test_hysteresis_and_unknown(self):
        self.record([(self.now+i,'timeout',None,'') for i in range(3)])
        with m.database() as db:
            self.assertEqual(db.execute('SELECT state FROM devices').fetchone()[0],'DOWN')
            incident=db.execute('SELECT * FROM incidents').fetchone()
            self.assertEqual((incident['start'],incident['failures']),(self.now,3))
        self.record([(self.now+3,'ok',5,''),(self.now+4,'ok',6,'')])
        with m.database() as db:
            self.assertIsNotNone(db.execute('SELECT end FROM incidents').fetchone()[0])
        self.record([(self.now+5,'dns',None,'DNS')])
        with m.database() as db:self.assertEqual(db.execute('SELECT state FROM devices').fetchone()[0],'UNKNOWN')
    def test_utc_midnight_and_dst(self):
        # UTC epochs spanning midnight / a European DST transition remain ordered.
        timestamps=[1792886399,1792886401,1792890001]
        self.record([(t,'ok',v,'') for t,v in zip(timestamps,[10,450,12])])
        with m.database() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM aggregates WHERE resolution=86400').fetchone()[0],2)
            self.assertEqual(db.execute('SELECT max_ts FROM aggregates WHERE resolution=86400 AND max_rtt=450').fetchone()[0],timestamps[1])
    def test_migration_idempotent_and_validation(self):
        m.migrate()
        for bad in [{'address':'-c 5'}, {'interval':'nan'}, {'probes':1.5}, {'interval':5,'probes':5,'timeout':5}, {'address':'a;id'}]:
            with self.assertRaises(ValueError):m.validate(dict(name='x',address='example.org',**{k:v for k,v in bad.items() if k!='address'}) if 'address' not in bad else dict(name='x',**bad))
    def test_scheduler_bounded_no_overlap_and_edit(self):
        scheduler=m.Scheduler(workers=2)
        try:
            futures=[]
            def submit(*args):
                f=Future();futures.append(f);return f
            with patch.object(scheduler.pool,'submit',side_effect=submit):
                devices=[dict(id=i,interval=5) for i in range(128)]
                scheduler.tick(devices,0);self.assertEqual(len(futures),2)
                scheduler.tick(devices,10);self.assertEqual(len(futures),2)
                futures[0].set_result([(1,'ok',3,'')]);devices[0]['interval']=10
                self.assertEqual(scheduler.tick(devices,11),[])
                self.assertEqual(len(scheduler.pending),2)
        finally:scheduler.pool.shutdown(wait=False,cancel_futures=True)
    def test_restart_and_gap_do_not_report_network_loss(self):
        self.record([(self.now+i,'timeout',None,'') for i in range(3)])
        with m.database() as db:
            m.reset_collector(db)
            self.assertEqual(db.execute('SELECT state FROM devices').fetchone()[0],'UNKNOWN')
            incident=db.execute('SELECT * FROM incidents').fetchone()
            self.assertEqual(incident['end_reason'],'monitoring_gap')
        self.record([(self.now+600,'ok',12,'')])
        with m.database() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM samples WHERE outcome='not_measured'").fetchone()[0],1)
            self.assertEqual(db.execute('SELECT sum(losses) FROM aggregates WHERE resolution=60').fetchone()[0],3)
    def test_alarm_deduplication_and_maintenance(self):
        self.record([(self.now+i,'ok',600,'') for i in range(5)])
        with m.database() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM alarms WHERE kind='rtt' AND active=1").fetchone()[0],1)
            m.save_device(db,dict(name='Router',address='192.0.2.1',maintenance_until=self.now+3600),self.id)
        self.record([(self.now+10,'ok',700,'')])
        with m.database() as db:
            self.assertEqual(db.execute("SELECT active FROM alarms WHERE kind='rtt' ORDER BY id DESC LIMIT 1").fetchone()[0],0)
    def test_probe_argument_safety_and_real_values(self):
        d=m.validate(dict(name='x',address='::1',probes=2))
        with patch.object(m.shutil,'which',return_value='/usr/bin/fping'),patch.object(m.subprocess,'run',return_value=SimpleNamespace(returncode=0,stderr='::1 : 450.125',stdout='')) as run:
            results=m.probe(d)
            self.assertEqual(len(results),2);self.assertEqual(results[0][2],450.125)
            self.assertEqual(run.call_args.args[0][-2:],['--','::1'])
            self.assertNotIn('shell',run.call_args.kwargs)

if __name__=='__main__':unittest.main()
