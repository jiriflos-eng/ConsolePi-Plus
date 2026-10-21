"""Bounded ICMP collector and SQLite store; timestamps are Unix UTC seconds."""
import csv
import io
import ipaddress
import json
import math
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path('/var/lib/consolepi-ping/monitor.sqlite3')
RELEVANT = ('ok', 'timeout', 'unreachable')
RESOLUTIONS = ((60, 30*86400), (300, 90*86400), (3600, 730*86400), (86400, 730*86400))
DEFAULTS = dict(name='', address='', description='', group_name='', tags='', interval=30,
                timeout=1, probes=1, warn_rtt=100, critical_rtt=500, loss_threshold=20,
                down_after=3, up_after=2, peak_factor=3, outage_seconds=0,
                paused=0, maintenance_start=0, maintenance_until=0)

@contextmanager
def database(path=None):
    db = sqlite3.connect(str(path or DB_PATH), timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA busy_timeout=10000')
    db.execute('PRAGMA foreign_keys=ON')
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def migrate(path=None):
    with database(path) as db:
        db.execute('PRAGMA journal_mode=WAL')
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version > 2:
            raise RuntimeError('Nepodporovaná verze databáze')
        if version == 2:
            return
        if version == 0:
            db.executescript('''
        CREATE TABLE config (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO config VALUES ('enabled','false');
        CREATE TABLE devices (
          id INTEGER PRIMARY KEY, name TEXT NOT NULL, address TEXT NOT NULL,
          description TEXT NOT NULL, group_name TEXT NOT NULL, tags TEXT NOT NULL,
          interval REAL NOT NULL, timeout REAL NOT NULL, probes INTEGER NOT NULL,
          warn_rtt REAL NOT NULL, critical_rtt REAL NOT NULL, loss_threshold REAL NOT NULL,
          down_after INTEGER NOT NULL, up_after INTEGER NOT NULL, peak_factor REAL NOT NULL,
          outage_seconds REAL NOT NULL, paused INTEGER NOT NULL, maintenance_start REAL NOT NULL, maintenance_until REAL NOT NULL,
          state TEXT NOT NULL DEFAULT 'UNKNOWN', last_ts REAL, last_ok REAL, rtt REAL,
          failures INTEGER NOT NULL DEFAULT 0, successes INTEGER NOT NULL DEFAULT 0,
          fail_start REAL, baseline REAL);
        CREATE TABLE samples (id INTEGER PRIMARY KEY, device_id INTEGER NOT NULL REFERENCES devices ON DELETE CASCADE,
          ts REAL NOT NULL, outcome TEXT NOT NULL, rtt REAL, error TEXT);
        CREATE INDEX samples_device_ts ON samples(device_id,ts);
        CREATE INDEX samples_ts ON samples(ts);
        CREATE TABLE aggregates (device_id INTEGER NOT NULL REFERENCES devices ON DELETE CASCADE,
          resolution INTEGER NOT NULL, bucket INTEGER NOT NULL, attempts INTEGER NOT NULL,
          successes INTEGER NOT NULL, losses INTEGER NOT NULL, unknowns INTEGER NOT NULL,
          min_rtt REAL, min_ts REAL, max_rtt REAL, max_ts REAL, total_rtt REAL NOT NULL,
          jitter_sum REAL NOT NULL, jitter_n INTEGER NOT NULL, first_ts REAL NOT NULL,
          last_ts REAL NOT NULL, first_rtt REAL, last_rtt REAL,
          PRIMARY KEY(device_id,resolution,bucket));
        CREATE TABLE peaks (id INTEGER PRIMARY KEY, device_id INTEGER NOT NULL REFERENCES devices ON DELETE CASCADE,
          ts REAL NOT NULL, rtt REAL NOT NULL);
        CREATE INDEX peaks_device_ts ON peaks(device_id,ts);
        CREATE TABLE incidents (id INTEGER PRIMARY KEY, device_id INTEGER NOT NULL REFERENCES devices ON DELETE CASCADE,
          start REAL NOT NULL, end REAL, failures INTEGER NOT NULL, acknowledged INTEGER NOT NULL DEFAULT 0, end_reason TEXT NOT NULL DEFAULT 'recovery');
        CREATE INDEX incidents_device_start ON incidents(device_id,start);
        CREATE TABLE alarms (id INTEGER PRIMARY KEY, device_id INTEGER NOT NULL REFERENCES devices ON DELETE CASCADE,
          ts REAL NOT NULL, kind TEXT NOT NULL, active INTEGER NOT NULL, detail TEXT NOT NULL);
        CREATE INDEX alarms_device_ts ON alarms(device_id,ts);
        PRAGMA user_version=1;
        ''')
        db.executescript('''
        BEGIN IMMEDIATE;
        CREATE TABLE IF NOT EXISTS collection_pauses (
          id INTEGER PRIMARY KEY, device_id INTEGER REFERENCES devices ON DELETE CASCADE,
          start REAL NOT NULL, end REAL, reason TEXT NOT NULL CHECK(reason IN ('disabled','paused')));
        CREATE UNIQUE INDEX IF NOT EXISTS collection_pause_open ON collection_pauses(IFNULL(device_id,0)) WHERE end IS NULL;
        CREATE INDEX IF NOT EXISTS collection_pause_time ON collection_pauses(start,end);
        PRAGMA user_version=2;
        COMMIT;
        ''')
        # Earlier switch times were not recorded. Seed only the state known now.
        now = time.time()
        if not enabled(db):
            collection_pause(db,None,True,now)
        for row in db.execute('SELECT id FROM devices WHERE paused=1').fetchall():
            collection_pause(db,row['id'],True,now)



def enabled(db):
    return db.execute("SELECT value FROM config WHERE key='enabled'").fetchone()[0] == 'true'


def collection_pause(db, device_id, active, now=None):
    ts = time.time() if now is None else now
    if active:
        db.execute('INSERT OR IGNORE INTO collection_pauses(device_id,start,reason) VALUES (?,?,?)',
                   (device_id,ts,'disabled' if device_id is None else 'paused'))
    else:
        db.execute('UPDATE collection_pauses SET end=? WHERE device_id IS ? AND end IS NULL',(ts,device_id))


def set_enabled(db, on, now=None):
    if enabled(db) == on:
        return
    ts = time.time() if now is None else now
    collection_pause(db,None,not on,ts)
    db.execute("UPDATE config SET value=? WHERE key='enabled'", ('true' if on else 'false',))
    db.execute("UPDATE devices SET state='UNKNOWN',failures=0,successes=0,fail_start=NULL")
    db.execute("UPDATE incidents SET end_reason='monitoring_gap',end=(SELECT last_ts FROM devices WHERE devices.id=incidents.device_id) WHERE end IS NULL")
    db.execute("INSERT INTO alarms(device_id,ts,kind,active,detail) SELECT a.device_id,?,a.kind,0,'Změna nastavení sběru' FROM alarms a WHERE active=1 AND id=(SELECT max(b.id) FROM alarms b WHERE b.device_id=a.device_id AND b.kind=a.kind)", (ts,))


def validate(data):
    result = dict(DEFAULTS)
    result.update({k: v for k, v in data.items() if k in DEFAULTS})
    for key, limit in [('name',120), ('address',253), ('description',1000), ('group_name',120), ('tags',500)]:
        result[key] = str(result[key]).strip()
        if len(result[key]) > limit:
            raise ValueError('Příliš dlouhá hodnota: ' + key)
    if not result['name'] or not result['address']:
        raise ValueError('Vyplňte název a adresu')
    address = result['address']
    try:
        ipaddress.ip_address(address)
        if '%' in address:
            raise ValueError('Scoped adresy nejsou podporovány')
    except ValueError:
        if not re.fullmatch(r'(?=.{1,253}\Z)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.?', address):
            raise ValueError('Neplatná IP adresa nebo hostname')
    bounds = dict(interval=(5,3600), timeout=(0.1,5), probes=(1,5), warn_rtt=(1,60000),
                  critical_rtt=(1,60000), loss_threshold=(1,100), down_after=(1,20),
                  up_after=(1,20), peak_factor=(1.1,100), outage_seconds=(0,86400),
                  paused=(0,1), maintenance_start=(0,4102444800), maintenance_until=(0,4102444800))
    for key, (low, high) in bounds.items():
        try:
            value = float(result[key])
        except (ValueError, TypeError):
            raise ValueError('Neplatné číslo: ' + key)
        if not math.isfinite(value) or not low <= value <= high:
            raise ValueError('Hodnota mimo rozsah: ' + key)
        if key in ('probes','down_after','up_after','paused'):
            if value != int(value):
                raise ValueError('Vyžadováno celé číslo: ' + key)
            value = int(value)
        result[key] = value
    if result['maintenance_until'] and result['maintenance_until'] <= result['maintenance_start']:
        raise ValueError('Konec údržby musí být po začátku')
    if result['warn_rtt'] > result['critical_rtt'] or result['probes'] * (result['timeout'] + .1) > result['interval']:
        raise ValueError('Zkontrolujte prahy RTT a délku cyklu vůči intervalu')
    return result


def save_device(db, data, device_id=None):
    values = validate(data)
    configs = [dict(r) for r in db.execute('SELECT * FROM devices') if r['id'] != device_id and not r['paused']]
    if not values['paused']:
        configs.append(values)
    if sum(d['probes']*(d['timeout']+.05)/d['interval'] for d in configs)>3 or sum(d['probes']/d['interval'] for d in configs)>8:
        raise ValueError('Překročen bezpečný rozpočet sond. Prodlužte intervaly nebo snižte timeout / počet sond.')
    if device_id is None:
        if db.execute('SELECT count(*) FROM devices').fetchone()[0] >= 128:
            raise ValueError('Limit 128 zařízení')
        keys = ','.join(values)
        saved = db.execute(f"INSERT INTO devices ({keys}) VALUES ({','.join('?' for _ in values)})", tuple(values.values())).lastrowid
        collection_pause(db,saved,bool(values['paused']))
        return saved
    if not db.execute('SELECT id FROM devices WHERE id=?', (device_id,)).fetchone():
        raise ValueError('Zařízení neexistuje')
    db.execute("UPDATE incidents SET end_reason='monitoring_gap',end=(SELECT last_ts FROM devices WHERE id=?) WHERE device_id=? AND end IS NULL", (device_id,device_id))
    for kind in ('rtt','loss','down'):
        alarm(db,device_id,kind,False,time.time(),'Změna konfigurace')
    db.execute('UPDATE devices SET ' + ','.join(k+'=?' for k in values) + ',state=\'UNKNOWN\', failures=0,successes=0,fail_start=NULL WHERE id=?', (*values.values(), device_id))
    collection_pause(db,device_id,bool(values['paused']))
    return device_id


def alarm(db, device_id, kind, active, ts, detail):
    previous = db.execute('SELECT active FROM alarms WHERE device_id=? AND kind=? ORDER BY id DESC LIMIT 1', (device_id,kind)).fetchone()
    if (bool(previous[0]) if previous else False) != active:
        db.execute('INSERT INTO alarms(device_id,ts,kind,active,detail) VALUES (?,?,?,?,?)', (device_id,ts,kind,int(active),detail))


def record(db, device_id, samples):
    row = db.execute('SELECT * FROM devices WHERE id=?', (device_id,)).fetchone()
    if not row or row['paused']:
        return
    d = dict(row)
    for ts, outcome, rtt, error in samples:
        if outcome != 'not_measured' and d['last_ts'] and ts-d['last_ts']>d['interval']*2:
            record(db,device_id,[(d['last_ts']+d['interval'],'not_measured',None,'Mezera sběru')])
            d = dict(db.execute('SELECT * FROM devices WHERE id=?',(device_id,)).fetchone())
        if outcome not in ('ok','timeout','unreachable','dns','internal','not_measured'):
            raise ValueError('Neznámý výsledek')
        if outcome != 'ok':
            rtt = None
        if outcome == 'ok' and (rtt is None or not math.isfinite(rtt) or rtt < 0):
            raise ValueError('Neplatné RTT')
        db.execute('INSERT INTO samples(device_id,ts,outcome,rtt,error) VALUES (?,?,?,?,?)', (device_id,ts,outcome,rtt,error))
        success = int(outcome == 'ok')
        loss = int(outcome in ('timeout','unreachable'))
        unknown = int(not success and not loss)
        previous_rtt = d['rtt'] if d['last_ts'] and ts-d['last_ts'] <= d['interval']*2 else None
        jitter = abs(rtt-previous_rtt) if rtt is not None and previous_rtt is not None else None
        for resolution, _ in RESOLUTIONS:
            bucket = int(ts//resolution)*resolution
            db.execute('''INSERT INTO aggregates VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
              ON CONFLICT(device_id,resolution,bucket) DO UPDATE SET
              attempts=attempts+excluded.attempts,successes=successes+excluded.successes,
              losses=losses+excluded.losses,unknowns=unknowns+excluded.unknowns,
              min_ts=CASE WHEN min_rtt IS NULL OR excluded.min_rtt<min_rtt THEN excluded.min_ts ELSE min_ts END,
              min_rtt=CASE WHEN min_rtt IS NULL OR excluded.min_rtt<min_rtt THEN excluded.min_rtt ELSE min_rtt END,
              max_ts=CASE WHEN max_rtt IS NULL OR excluded.max_rtt>max_rtt THEN excluded.max_ts ELSE max_ts END,
              max_rtt=CASE WHEN max_rtt IS NULL OR excluded.max_rtt>max_rtt THEN excluded.max_rtt ELSE max_rtt END,
              total_rtt=total_rtt+excluded.total_rtt,jitter_sum=jitter_sum+excluded.jitter_sum,
              jitter_n=jitter_n+excluded.jitter_n,last_ts=excluded.last_ts,last_rtt=excluded.last_rtt''',
              (device_id,resolution,bucket,success+loss,success,loss,unknown,rtt,ts if success else None,
               rtt,ts if success else None,rtt or 0,jitter or 0,int(jitter is not None),ts,ts,rtt,rtt))
        if success:
            if rtt >= d['critical_rtt'] or (d['baseline'] is not None and rtt >= max(d['warn_rtt'], d['baseline']*d['peak_factor'])):
                db.execute('INSERT INTO peaks(device_id,ts,rtt) VALUES (?,?,?)', (device_id,ts,rtt))
            d['baseline'] = rtt if d['baseline'] is None else .95*d['baseline']+.05*rtt
            d['successes'] += 1
            d['failures'] = 0
            d['last_ok'] = ts
            if d['successes'] >= d['up_after']:
                db.execute('UPDATE incidents SET end=? WHERE device_id=? AND end IS NULL', (ts,device_id))
                d['fail_start'] = None
                d['state'] = 'DEGRADED' if rtt >= d['warn_rtt'] else 'UP'
        elif loss:
            if d['failures'] == 0:
                d['fail_start'] = ts
            d['failures'] += 1
            d['successes'] = 0
            if d['failures'] >= d['down_after']:
                d['state'] = 'DOWN'
                if not db.execute('SELECT id FROM incidents WHERE device_id=? AND end IS NULL', (device_id,)).fetchone():
                    db.execute('INSERT INTO incidents(device_id,start,failures) VALUES (?,?,?)', (device_id,d['fail_start'],d['failures']-1))
            db.execute('UPDATE incidents SET failures=failures+1 WHERE device_id=? AND end IS NULL', (device_id,))
        else:
            d.update(state='UNKNOWN', failures=0, successes=0, fail_start=None)
            # Collector/DNS uncertainty interrupts outage duration evidence.
            db.execute("UPDATE incidents SET end=?,end_reason='monitoring_gap' WHERE device_id=? AND end IS NULL", (ts,device_id))
        d.update(last_ts=ts,rtt=rtt)
        recent = db.execute("SELECT outcome FROM samples WHERE device_id=? AND outcome IN ('ok','timeout','unreachable') ORDER BY ts DESC,id DESC LIMIT 20", (device_id,)).fetchall()
        loss_pct = 100*sum(r[0] != 'ok' for r in recent)/len(recent) if recent else 0
        if d['state'] == 'UP' and loss_pct >= d['loss_threshold']:
            d['state'] = 'DEGRADED'
        maintenance = d['maintenance_start'] <= ts < d['maintenance_until']
        for kind, active in [('rtt',success and rtt >= d['warn_rtt']), ('loss',loss_pct >= d['loss_threshold']),
                             ('down',d['state']=='DOWN' and ts-(d['fail_start'] or ts)>=d['outage_seconds'])]:
            alarm(db,device_id,kind,bool(active and not maintenance and d['state']!='UNKNOWN'),ts,d['state'])
    keys = ('state','last_ts','last_ok','rtt','failures','successes','fail_start','baseline')
    db.execute('UPDATE devices SET '+','.join(k+'=?' for k in keys)+' WHERE id=?', (*[d[k] for k in keys],device_id))


def cleanup(db, now):
    # All resolutions are updated in the same transaction as raw insertion.
    db.execute('DELETE FROM samples WHERE ts<?', (now-7*86400,))
    for resolution, retention in RESOLUTIONS:
        db.execute('DELETE FROM aggregates WHERE resolution=? AND bucket<?', (resolution,now-retention))
    db.execute('DELETE FROM collection_pauses WHERE end IS NOT NULL AND end<?', (now-730*86400,))
    for table, column in [('peaks','ts'),('incidents','start'),('alarms','ts')]:
        extra = ' AND end IS NOT NULL' if table == 'incidents' else ''
        db.execute(f'DELETE FROM {table} WHERE {column}<?{extra}', (now-730*86400,))


def statistics(db, device_id, start, end):
    duration = end-start
    resolution = 60 if duration <= 30*86400 else 300 if duration <= 90*86400 else 3600
    r = dict(db.execute('''SELECT sum(attempts) attempts,sum(successes) successes,sum(losses) losses,
       max(max_rtt) max_rtt,min(min_rtt) min_rtt,sum(total_rtt) total_rtt,
       sum(jitter_sum) jitter_sum,sum(jitter_n) jitter_n FROM aggregates
       WHERE device_id=? AND resolution=? AND bucket>=? AND bucket<?''', (device_id,resolution,int(start//resolution)*resolution,end)).fetchone())
    r['loss'] = 100*(r['losses'] or 0)/r['attempts'] if r['attempts'] else None
    r['uptime'] = 100*(r['successes'] or 0)/r['attempts'] if r['attempts'] else None
    r['jitter'] = r['jitter_sum']/r['jitter_n'] if r['jitter_n'] else None
    r['incidents'] = db.execute('SELECT count(*) FROM incidents WHERE device_id=? AND start<? AND (end IS NULL OR end>=?)', (device_id,end,start)).fetchone()[0]
    return r


def overview(db, start, end):
    now = time.time()
    running = enabled(db)
    heartbeat = db.execute("SELECT value FROM config WHERE key='heartbeat'").fetchone()
    healthy = running and heartbeat and now-float(heartbeat[0]) < 30
    devices = []
    for row in db.execute('SELECT * FROM devices ORDER BY name'):
        d = dict(row)
        if d['paused']:
            d['state'] = 'PAUSED'
        elif not healthy or not d['last_ts'] or now-d['last_ts'] > max(30,d['interval']*2):
            d['state'] = 'UNKNOWN'
        d['stats'] = statistics(db,d['id'],start,end)
        devices.append(d)
    return dict(enabled=running, healthy=bool(healthy), devices=devices,
                counts={s:sum(d['state']==s for d in devices) for s in ('UP','DOWN','DEGRADED','UNKNOWN','PAUSED')},
                database_bytes=sum(p.stat().st_size for p in DB_PATH.parent.glob('monitor.sqlite3*') if p.is_file()))


def history(db, device_id, start, end, limit=None):
    duration = end-start
    if limit is None:
        limit = 96 if duration >= 48*3600 else 600
    resolution = 0 if start >= time.time()-7*86400 and duration <= 3600 else 60 if start >= time.time()-30*86400 else 300 if start >= time.time()-90*86400 else 3600
    bucket_size = max(resolution or 1, math.ceil(duration/max(1,min(limit,1000))))
    if duration >= 28*86400:
        resolution = 86400
        bucket_size = max(bucket_size,86400)
    if resolution:
        bucket_size = math.ceil(bucket_size/resolution)*resolution
    buckets = {}
    if resolution == 0:
        source = db.execute('SELECT ts,outcome,rtt FROM samples WHERE device_id=? AND ts>=? AND ts<? ORDER BY ts,id', (device_id,start,end))
        iterator = (dict(first_ts=r['ts'],last_ts=r['ts'], min_rtt=r['rtt'],max_rtt=r['rtt'],min_ts=r['ts'] if r['rtt'] is not None else None,max_ts=r['ts'] if r['rtt'] is not None else None,
                         attempts=int(r['outcome'] in RELEVANT),successes=int(r['outcome']=='ok'),losses=int(r['outcome'] in ('timeout','unreachable')),unknowns=int(r['outcome'] not in RELEVANT),total_rtt=r['rtt'] or 0,jitter_sum=0,jitter_n=0) for r in source)
    else:
        iterator = (dict(r) for r in db.execute('SELECT * FROM aggregates WHERE device_id=? AND resolution=? AND bucket>=? AND bucket<? ORDER BY bucket', (device_id,resolution,int(start//resolution)*resolution,end)))
    previous = None
    interval = db.execute('SELECT interval FROM devices WHERE id=?',(device_id,)).fetchone()
    interval = interval[0] if interval else 30
    for r in iterator:
        if resolution == 0:
            if previous and r['min_rtt'] is not None and previous['min_rtt'] is not None and r['first_ts']-previous['last_ts']<=interval*2:
                r['jitter_sum'] = abs(r['min_rtt']-previous['min_rtt'])
                r['jitter_n'] = 1
            previous = dict(r)
        key = int(r['first_ts']//bucket_size)*bucket_size
        if key not in buckets:
            buckets[key] = dict(r, bucket=key)
            continue
        b = buckets[key]
        for kind in ('min','max'):
            val = r[kind+'_rtt']
            if val is not None and (b[kind+'_rtt'] is None or (val < b[kind+'_rtt'] if kind=='min' else val > b[kind+'_rtt'])):
                b[kind+'_rtt'], b[kind+'_ts'] = val,r[kind+'_ts']
        for k in ('attempts','successes','losses','unknowns','total_rtt','jitter_sum','jitter_n'):
            b[k] += r[k]
        b['last_ts'] = r['last_ts']
    result = []
    for b in buckets.values():
        points = {(b[k+'_ts'],b[k+'_rtt']) for k in ('min','max') if b[k+'_rtt'] is not None}
        b['points'] = sorted(points)
        b['typical_rtt'] = b['total_rtt']/b['successes'] if b['successes'] else None
        b['loss'] = 100*b['losses']/b['attempts'] if b['attempts'] else None
        b['jitter'] = b['jitter_sum']/b['jitter_n'] if b['jitter_n'] else None
        result.append(b)
    incidents = [dict(r) for r in db.execute('SELECT * FROM incidents WHERE device_id=? AND start<? AND (end IS NULL OR end>=?) ORDER BY start DESC LIMIT 500',(device_id,end,start))]
    pauses = [dict(r) for r in db.execute('SELECT start,end,reason FROM collection_pauses WHERE (device_id IS NULL OR device_id=?) AND start<? AND (end IS NULL OR end>?) ORDER BY start',(device_id,end,start))]
    return dict(buckets=result,resolution=resolution,bucket_size=bucket_size,start=start,end=end,incidents=incidents,pauses=pauses)


def probe(device):
    """Each probe is timestamped at actual dispatch; no synthetic times."""
    executable = shutil.which('fping') or shutil.which('ping')
    if not executable:
        return [(time.time(),'internal',None,'Chybí fping i iputils-ping')]
    results = []
    for _ in range(device['probes']):
        ts = time.time()
        fping = Path(executable).name == 'fping'
        args = ([executable,'-C','1','-q','-r','0','-t',str(int(device['timeout']*1000)), '--',device['address']] if fping else
                [executable,'-n','-c','1','-W',str(max(1,math.ceil(device['timeout']))), '--',device['address']])
        try:
            result = subprocess.run(args,capture_output=True,text=True,timeout=device['timeout']+3,
                                    env={**os.environ,'LC_ALL':'C'})
            output = result.stderr+'\n'+result.stdout
            match = re.search(r':\s*(\d+(?:\.\d+)?)\s*$',output.strip()) if fping else re.search(r'time[=<](\d+(?:\.\d+)?)\s*ms',output)
            if result.returncode == 0 and match:
                results.append((ts,'ok',float(match.group(1)),''))
            else:
                kind = ('dns' if (fping and result.returncode == 2) or re.search('resolve|not known|not found|Name or service|Temporary failure',output,re.I) else
                        'unreachable' if 'unreachable' in output.lower() else
                        'timeout' if result.returncode == 1 else 'internal')
                results.append((ts,kind,None,output[-500:]))
        except (OSError,subprocess.TimeoutExpired) as exc:
            results.append((ts,'internal',None,str(exc)[:500]))
    return results


class Scheduler:
    def __init__(self, workers=4):
        self.pool = ThreadPoolExecutor(max_workers=workers)
        self.workers = workers
        self.pending = {}
        self.due = {}

    def tick(self, devices, now):
        completed = []
        current = {d['id']:d for d in devices}
        for device_id,(future,original) in list(self.pending.items()):
            if future.done():
                if current.get(device_id) == original:
                    completed.append((device_id,future.result()))
                del self.pending[device_id]
        self.due = {k:v for k,v in self.due.items() if k in current}
        for d in sorted(devices,key=lambda d:self.due.get(d['id'],0)):
            key = d['id']
            if key in self.pending or now < self.due.get(key,0):
                continue
            if len(self.pending) >= self.workers:
                break
            self.pending[key] = (self.pool.submit(probe,d),dict(d))
            self.due[key] = now+d['interval']
        return completed


def reset_collector(db):
    db.execute("UPDATE devices SET state='UNKNOWN', failures=0,successes=0,fail_start=NULL")
    # A restart is an unknown gap, not continued evidence of downtime.
    db.execute("UPDATE incidents SET end_reason='monitoring_gap',end=(SELECT last_ts FROM devices WHERE devices.id=incidents.device_id) WHERE end IS NULL")
    db.execute("INSERT INTO alarms(device_id,ts,kind,active,detail) SELECT a.device_id,?,a.kind,0,'Restart sběru' FROM alarms a WHERE active=1 AND id=(SELECT max(b.id) FROM alarms b WHERE b.device_id=a.device_id AND b.kind=a.kind)", (time.time(),))


def run():
    import fcntl
    DB_PATH.parent.mkdir(parents=True,exist_ok=True)
    with (DB_PATH.parent/'collector.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        migrate()
        stop = False
        def shutdown(*_):
            nonlocal stop
            stop = True
        signal.signal(signal.SIGTERM,shutdown)
        signal.signal(signal.SIGINT,shutdown)
        scheduler = Scheduler()
        last_cleanup = 0
        with database() as db:
            reset_collector(db)
        try:
            while not stop:
                with database() as db:
                    on = enabled(db)
                    devices = [dict(r) for r in db.execute('SELECT * FROM devices WHERE paused=0')] if on else []
                # Runtime counters are excluded from configuration identity.
                fields = ('id',*DEFAULTS.keys())
                configs = [{k:d[k] for k in fields} for d in devices]
                results = scheduler.tick(configs,time.monotonic())
                with database() as db:
                    if enabled(db):
                        for device_id,samples in results:
                            record(db,device_id,samples)
                    db.execute("INSERT INTO config VALUES ('heartbeat',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(time.time()),))
                    if time.monotonic()-last_cleanup >= 3600:
                        cleanup(db,time.time())
                        last_cleanup = time.monotonic()
                time.sleep(1)
        finally:
            scheduler.pool.shutdown(wait=True,cancel_futures=True)


if __name__ == '__main__':
    run()
