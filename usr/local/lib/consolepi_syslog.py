"""Bounded, asynchronous RFC 5424/5425 event forwarding (no transcripts)."""
import datetime
import fcntl
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import ssl
import subprocess
import sys
import threading
import time

CONFIG = Path('/etc/consolepi/syslog.json')
ROOT = Path('/var/lib/consolepi-syslog')
DB = ROOT / 'queue.sqlite3'
SERVICE = 'consolepi-syslog.service'
MAX_QUEUE = 2000
DEFAULTS = {'enabled': False, 'host': '', 'port': 6514, 'transport': 'tls',
            'severity': 6, 'ca_pem': ''}
PRIORITIES = ['emerg', 'alert', 'crit', 'err', 'warning', 'notice', 'info', 'debug']
LEVELS = ['Emergency', 'Alert', 'Critical', 'Error', 'Warning', 'Notice',
          'Informational', 'Debug']


def validate(values):
    if not isinstance(values, dict):
        raise ValueError('Neplatná konfigurace syslogu.')
    if type(values.get('enabled', False)) is not bool:
        raise ValueError('Neplatná hodnota zapnutí syslogu.')
    cfg = dict(DEFAULTS, **{k: values[k] for k in DEFAULTS if k in values})
    host = str(cfg['host']).strip()
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if host and (len(host) > 253 or not all(
                re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', p)
                for p in host.rstrip('.').split('.'))):
            raise ValueError('Zadejte IP adresu nebo DNS jméno serveru bez URL.')
    if cfg['enabled'] and not host:
        raise ValueError('Zadejte syslog server.')
    cfg['host'] = host
    try:
        cfg['port'] = int(cfg['port'])
        cfg['severity'] = int(cfg['severity'])
    except (ValueError, TypeError):
        raise ValueError('Neplatný port nebo severity.')
    if not 1 <= cfg['port'] <= 65535 or not 0 <= cfg['severity'] <= 7:
        raise ValueError('Port musí být 1–65535 a severity 0–7.')
    if cfg['transport'] not in ('tls', 'tcp'):
        raise ValueError('Podporované transporty jsou TLS a TCP.')
    pem = str(cfg['ca_pem']).strip()
    if len(pem) > 65536 or (pem and 'PRIVATE KEY' in pem):
        raise ValueError('Vložte pouze veřejný PEM certifikát CA, nikoli privátní klíč.')
    if pem:
        try:
            ssl.create_default_context(cadata=pem)
        except (ssl.SSLError, ValueError):
            raise ValueError('Neplatný PEM certifikát CA.')
    cfg['ca_pem'] = pem
    return cfg


def load():
    return validate(json.loads(CONFIG.read_text())) if CONFIG.exists() else dict(DEFAULTS)


def connect_db():
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(ROOT, 0o700)
    con = sqlite3.connect(DB, timeout=10)
    os.chmod(DB, 0o600)
    con.execute('CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, frame BLOB NOT NULL)')
    con.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
    con.commit()
    return con


def meta(con, key, default=''):
    row = con.execute('SELECT value FROM metadata WHERE key=?', (key,)).fetchone()
    return row[0] if row else default


def set_meta(con, key, value):
    con.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)', (key, str(value)))


def choose_event(entry, threshold):
    """Allowlisted producers only; never read transcript or arbitrary files."""
    tag = entry.get('SYSLOG_IDENTIFIER', '')
    msg = entry.get('MESSAGE', '')
    if not isinstance(msg, str):
        return None
    try:
        severity = int(entry.get('PRIORITY', 6))
    except (ValueError, TypeError):
        return None
    if not 0 <= severity <= 7:
        return None
    # OpenSSH commonly emits failed authentication at info: promote selected failures.
    if tag in ('sshd', 'sshd-session') and re.match(
            r'(Failed |Invalid user |error: PAM: Authentication failure|authentication failure)', msg):
        severity = min(severity, 4)
    allowed = tag in ('consolepi', 'sshd', 'sshd-session')
    allowed |= tag == 'kernel' and 'nft-input-drop' in msg
    # Web audit emits fixed event fields, separate from arbitrary Flask error output.
    allowed |= tag == 'consolepi-web-audit'
    allowed |= (tag == 'systemd' and severity <= 4 and bool(re.search(
        r'\b(?:consolepi-web|consolepi-port-monitor|nginx|ssh|nftables)\.service\b', msg)))
    if not allowed or severity > threshold:
        return None
    # Normalize control characters to prevent multiline/log framing injection.
    msg = ''.join(c if c.isprintable() else ' ' for c in msg)[:2048]
    return severity, tag, msg


def frame(entry, selected):
    severity, tag, msg = selected
    host = re.sub(r'[^A-Za-z0-9_.-]', '_', str(entry.get('_HOSTNAME', socket.gethostname())))[:255] or '-'
    tag = re.sub(r'[^A-Za-z0-9_.-]', '_', tag)[:48] or '-'
    try:
        date = datetime.datetime.fromtimestamp(int(entry['__REALTIME_TIMESTAMP']) / 1e6,
                                              datetime.timezone.utc).isoformat()
    except (KeyError, ValueError, TypeError, OverflowError):
        date = datetime.datetime.now(datetime.timezone.utc).isoformat()
    # authpriv facility 10; UTF-8 BOM marks the RFC 5424 MSG encoding.
    payload = f'<{80 + severity}>1 {date} {host} {tag} - - - \ufeff{msg}'.encode('utf-8')
    return str(len(payload)).encode('ascii') + b' ' + payload


def enqueue(con, entry, cfg):
    event = choose_event(entry, cfg['severity'])
    with con:
        if event:
            count = con.execute('SELECT count(*) FROM messages').fetchone()[0]
            if count >= MAX_QUEUE:
                # Drop oldest; reserve space for new events, never block console processes.
                con.execute('DELETE FROM messages WHERE id=(SELECT min(id) FROM messages)')
                set_meta(con, 'dropped', int(meta(con, 'dropped', '0')) + 1)
            con.execute('INSERT INTO messages(frame) VALUES (?)', (frame(entry, event),))
        if isinstance(entry.get('__CURSOR'), str):
            set_meta(con, 'cursor', entry['__CURSOR'])


def transmit(cfg, data):
    with socket.create_connection((cfg['host'], cfg['port']), timeout=5) as sock:
        if cfg['transport'] == 'tls':
            context = ssl.create_default_context(cadata=cfg['ca_pem'] or None)
            with context.wrap_socket(sock, server_hostname=cfg['host']) as secured:
                secured.sendall(data)
        else:
            sock.sendall(data)


def sender(cfg, stop):
    con = connect_db()
    try:
        while not stop.is_set():
            row = con.execute('SELECT id,frame FROM messages ORDER BY id LIMIT 1').fetchone()
            if row is None:
                stop.wait(1)
                continue
            try:
                transmit(cfg, row[1])
            except (OSError, ssl.SSLError) as exc:
                with con:
                    set_meta(con, 'state', 'retrying')
                    set_meta(con, 'error', str(exc)[:300])
                stop.wait(10)
            else:
                with con:
                    con.execute('DELETE FROM messages WHERE id=?', (row[0],))
                    set_meta(con, 'state', 'sent')
                    set_meta(con, 'error', '')
                    set_meta(con, 'last_sent', datetime.datetime.now(datetime.timezone.utc).isoformat())
    finally:
        con.close()


def supervised_sender(cfg, stop):
    try:
        sender(cfg, stop)
    except Exception as exc:
        # A failed worker must not leave a healthy-looking collector accumulating forever.
        print('Syslog sender failed: ' + str(exc), file=sys.stderr, flush=True)
        os._exit(1)  # systemd restarts; SQLite rolls back an incomplete transaction.


def daemon():
    cfg = load()
    if not cfg['enabled']:
        return
    con = connect_db()
    cursor = meta(con, 'cursor')
    args = ['journalctl', '--follow', '--output=json', '--no-pager']
    args += ['SYSLOG_IDENTIFIER=' + tag for tag in
             ('consolepi', 'sshd', 'sshd-session', 'kernel', 'consolepi-web-audit', 'systemd')]
    # An expired journal cursor must not silently prevent collection.
    if cursor and subprocess.run(['journalctl', '--cursor', cursor, '-n', '1', '--no-pager'],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        args += ['--after-cursor', cursor]
    else:
        args += ['--since=now']
    stop = threading.Event()
    worker = threading.Thread(target=supervised_sender, args=(cfg, stop), daemon=True)
    worker.start()
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, text=True)
    try:
        for line in proc.stdout:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            enqueue(con, entry, cfg)
        raise RuntimeError('journalctl unexpectedly stopped')
    finally:
        proc.terminate()
        stop.set()
        worker.join(timeout=6)
        con.close()


def _control(action, values=None):
    if action == 'status':
        cfg = load()
        con = connect_db()
        result = dict(cfg, pending=con.execute('SELECT count(*) FROM messages').fetchone()[0],
                      dropped=int(meta(con, 'dropped', '0')), state=meta(con, 'state', 'idle'),
                      error=meta(con, 'error'), last_sent=meta(con, 'last_sent'), levels=LEVELS,
                      running=subprocess.run(['systemctl', 'is-active', '--quiet', SERVICE]).returncode == 0)
        con.close()
        return result
    if action == 'test':
        cfg = load()
        if not cfg['enabled']:
            raise ValueError('Nejdříve zapněte a uložte vzdálený syslog.')
        subprocess.run(['logger', '-p', 'authpriv.' + PRIORITIES[cfg['severity']], '-t', 'consolepi', '--',
                        'SYSLOG_TEST version=1.9.1'], check=True)
        return {'message': 'Testovací událost byla zapsána; ověřte přijetí na syslog serveru.'}
    if action in ('configure', 'reset'):
        cfg = validate(values or {}) if action == 'configure' else dict(DEFAULTS)
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        previous = CONFIG.read_bytes() if CONFIG.exists() else None
        subprocess.run(['systemctl', 'stop', SERVICE], check=True)
        # Purge old destination's queue on any configuration change, including disabling.
        con = connect_db()
        with con:
            con.execute('DELETE FROM messages')
            con.execute('DELETE FROM metadata')
        con.execute('VACUUM')
        con.close()
        try:
            temp = CONFIG.with_suffix('.tmp')
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, 'w') as out:
                json.dump(cfg, out)
                out.write('\n')
                out.flush()
                os.fsync(out.fileno())
            os.replace(temp, CONFIG)
            if cfg['enabled']:
                subprocess.run(['systemctl', 'enable', '--now', SERVICE], check=True)
            else:
                subprocess.run(['systemctl', 'disable', SERVICE], check=True)
        except Exception:
            if previous is None:
                CONFIG.unlink(missing_ok=True)
            else:
                CONFIG.write_bytes(previous)
                os.chmod(CONFIG, 0o600)
            if previous and json.loads(previous).get('enabled'):
                subprocess.run(['systemctl', 'restart', SERVICE], check=False)
            else:
                subprocess.run(['systemctl', 'disable', '--now', SERVICE], check=False)
            raise
        subprocess.run(['logger', '-p', 'authpriv.notice', '-t', 'consolepi', '--',
                        f'SYSLOG_CONFIG enabled={cfg["enabled"]} severity={cfg["severity"]}'], check=True)
        return {'message': 'Nastavení syslogu uloženo.'}
    raise ValueError('Nepovolená operace syslogu.')

def control(action, values=None):
    if action == 'status':
        return _control(action, values)
    with open('/run/lock/consolepi-syslog-config.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _control(action, values)


if __name__ == '__main__':
    daemon()
