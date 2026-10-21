"""Routes use the parent application's existing session and CSRF token."""
import csv
import io
import math
import secrets
import sqlite3
import time
from functools import wraps
from flask import Blueprint, jsonify, redirect, render_template, request, session, Response, url_for, abort
import ping_monitor as monitor


def register(app, authenticated):
    bp = Blueprint('ping',__name__)

    @bp.before_request
    def protect():
        if request.method == 'GET' and request.endpoint in {'ping.public_summary','ping.public_history','ping.public_detail'}:
            return None
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        if request.method != 'GET':
            token = request.headers.get('X-CSRF-Token',request.form.get('csrf',''))
            if not session.get('csrf') or not secrets.compare_digest(session['csrf'],token):
                return jsonify(error='Neplatný CSRF token'),403

    @bp.after_request
    def prevent_public_cache(response):
        if request.path.startswith(('/ping/public/','/ping/view/')):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @bp.errorhandler(ValueError)
    def invalid(error):
        return jsonify(error=str(error)),400

    @bp.errorhandler(sqlite3.Error)
    def unavailable(error):
        app.logger.exception('Ping databáze není dostupná')
        return jsonify(error='Databáze monitoru není dostupná. Zkontrolujte instalaci a službu.'),503

    def payload():
        value = request.get_json(silent=True) if request.is_json else request.form.to_dict()
        if not isinstance(value,dict):
            raise ValueError('Očekáván objekt JSON')
        return value

    def period():
        now = time.time()
        try:
            end = float(request.args.get('end',now))
            start = float(request.args.get('start',end-float(request.args.get('period',3600))))
        except (ValueError,TypeError):
            raise ValueError('Neplatné období')
        if not all(math.isfinite(x) for x in (start,end)) or not 1 <= end-start <= 366*86400 or end > now+60 or start < now-731*86400:
            raise ValueError('Období musí být 1 sekunda až 1 rok v uchované historii')
        return start,end

    def history_limit():
        value = request.args.get('buckets')
        if value is None:
            return None
        try:
            value = int(value)
        except (ValueError,TypeError):
            raise ValueError('Neplatný počet intervalů grafu')
        if not 1 <= value <= 1000:
            raise ValueError('Počet intervalů grafu musí být 1–1000')
        return value

    def public_device(d):
        # Explicit read-only projection; configuration, addresses and raw errors stay private.
        return {k:d[k] for k in ('id','name','state','rtt','last_ok','stats')}

    @bp.get('/ping/public/summary')
    def public_summary():
        start,end = period()
        try:
            with monitor.database() as db:
                if not monitor.enabled(db):
                    return jsonify(enabled=False,devices=[])
                result = monitor.overview(db,start,end)
                devices = []
                for d in result['devices']:
                    item = public_device(d)
                    item['sparkline'] = [dict(r) for r in db.execute(
                        'SELECT min_ts,min_rtt,max_ts,max_rtt,losses,unknowns FROM aggregates WHERE device_id=? AND resolution=60 AND bucket>=? ORDER BY bucket',
                        (d['id'],time.time()-900))]
                    devices.append(item)
                response = jsonify(enabled=True,healthy=result['healthy'],counts=result['counts'],devices=devices)
                response.headers['Cache-Control'] = 'no-store'
                return response
        except sqlite3.Error:
            # A disabled/uninstalled optional module must not break the landing page.
            return jsonify(enabled=False,devices=[])

    @bp.get('/ping/view/<int:device_id>')
    def public_detail(device_id):
        with monitor.database() as db:
            if not monitor.enabled(db) or not db.execute('SELECT id FROM devices WHERE id=?',(device_id,)).fetchone():
                abort(404)
        return render_template('ping_detail.html',device_id=device_id)

    @bp.get('/ping/public/history/<int:device_id>')
    def public_history(device_id):
        start,end = period()
        with monitor.database() as db:
            if not monitor.enabled(db) or not db.execute('SELECT id FROM devices WHERE id=?',(device_id,)).fetchone():
                abort(404)
            data = monitor.history(db,device_id,start,end,limit=history_limit())
            # Incidents are display-only: acknowledgement remains authenticated and CSRF protected.
            data['incidents'] = [{k:r[k] for k in ('start','end','end_reason','failures')} for r in data['incidents']]
            response = jsonify(data)
            response.headers['Cache-Control'] = 'no-store'
            return response

    @bp.get('/ping')
    @bp.get('/ping/<int:device_id>')
    def page(device_id=None):
        return render_template('ping.html',csrf=session['csrf'],device_id=device_id)

    @bp.get('/ping/api/overview')
    def overview():
        start,end = period()
        with monitor.database() as db:
            result = monitor.overview(db,start,end)
            group = request.args.get('group')
            if group:
                result['devices'] = [d for d in result['devices'] if d['group_name']==group]
            return jsonify(result)

    @bp.post('/ping/api/settings')
    def settings():
        data = payload()
        if type(data.get('enabled')) is not bool:
            raise ValueError('enabled musí být boolean')
        with monitor.database() as db:
            monitor.set_enabled(db,data['enabled'])
        return jsonify(enabled=data['enabled'])

    @bp.route('/ping/api/devices', methods=['GET','POST'])
    @bp.route('/ping/api/devices/<int:device_id>', methods=['POST','DELETE'])
    def device(device_id=None):
        with monitor.database() as db:
            if request.method == 'GET':
                heartbeat = db.execute("SELECT value FROM config WHERE key='heartbeat'").fetchone()
                running = monitor.enabled(db)
                return jsonify(enabled=running,healthy=bool(running and heartbeat and time.time()-float(heartbeat[0])<30),
                    devices=[{k:r[k] for k in ('id',*monitor.DEFAULTS)} for r in db.execute('SELECT * FROM devices ORDER BY name')])
            if request.method == 'DELETE':
                db.execute('DELETE FROM devices WHERE id=?', (device_id,))
                return jsonify(ok=True)
            data = payload()
            if device_id is not None:
                existing = db.execute('SELECT * FROM devices WHERE id=?',(device_id,)).fetchone()
                if not existing:
                    raise ValueError('Zařízení neexistuje')
                data = {**dict(existing),**data}
            saved = monitor.save_device(db,data,device_id)
        return jsonify(id=saved)

    @bp.get('/ping/api/history/<int:device_id>')
    def history(device_id):
        start,end = period()
        with monitor.database() as db:
            return jsonify(monitor.history(db,device_id,start,end,limit=history_limit()))

    @bp.get('/ping/api/events')
    def events():
        start,end = period()
        with monitor.database() as db:
            result = {}
            for table,column in [('incidents','start'),('peaks','ts'),('alarms','ts')]:
                result[table] = [dict(r) for r in db.execute(f'SELECT * FROM {table} WHERE {column}>=? AND {column}<? ORDER BY {column} DESC LIMIT 500', (start,end))]
            result['active_alarms'] = [dict(r) for r in db.execute('''SELECT a.* FROM alarms a JOIN devices d ON d.id=a.device_id
              WHERE a.active=1 AND d.paused=0 AND NOT (d.maintenance_start<=? AND d.maintenance_until>?)
              AND a.id=(SELECT max(b.id) FROM alarms b WHERE b.device_id=a.device_id AND b.kind=a.kind) LIMIT 500''', (time.time(),time.time()))]
            result['open_incidents'] = [dict(r) for r in db.execute('SELECT * FROM incidents WHERE end IS NULL LIMIT 128')]
            return jsonify(result)

    @bp.post('/ping/api/incidents/<int:incident_id>/ack')
    def acknowledge(incident_id):
        with monitor.database() as db:
            db.execute('UPDATE incidents SET acknowledged=1 WHERE id=?',(incident_id,))
        return jsonify(ok=True)

    @bp.route('/ping/api/csv', methods=['GET','POST'])
    def exchange():
        if request.method == 'GET':
            out = io.StringIO()
            writer = csv.DictWriter(out,fieldnames=list(monitor.DEFAULTS))
            writer.writeheader()
            with monitor.database() as db:
                for r in db.execute('SELECT * FROM devices ORDER BY id'):
                    # Prevent spreadsheet formula execution in exported text cells.
                    writer.writerow({k: "'"+r[k] if isinstance(r[k],str) and r[k].startswith(('=','+','-','@','\t','\r')) else r[k] for k in monitor.DEFAULTS})
            return Response(out.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=ping-devices.csv'})
        file = request.files.get('file')
        if file is None:
            raise ValueError('Chybí CSV soubor')
        raw = file.stream.read(256*1024+1)
        if len(raw)>256*1024:
            raise ValueError('CSV je příliš velké')
        try:
            reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
            rows = list(reader)
        except (UnicodeError,csv.Error):
            raise ValueError('Neplatné CSV UTF-8')
        if len(rows)>128 or not reader.fieldnames or not {'name','address'}.issubset(reader.fieldnames):
            raise ValueError('CSV vyžaduje name,address a nejvýše 128 řádků')
        with monitor.database() as db:
            for row in rows:
                monitor.save_device(db,row)
        return jsonify(imported=len(rows))

    app.register_blueprint(bp)
