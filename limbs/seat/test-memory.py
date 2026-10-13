#!/usr/bin/env python3
"""Checks of kimera-memory against a pretend door on this machine's loopback. Nothing leaves the machine."""
import http.server, json, os, subprocess, sys, tempfile, threading
HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN = 'T' * 44
seen, fails = [], 0
mode = {'v': 'ok', 'n429': 0}


class Door(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def answer(self, code, obj, raw=None):
        b = raw if raw is not None else json.dumps(obj).encode()
        self.send_response(code); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)

    def handle_any(self):
        n = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(n).decode() if n else ''
        seen.append((self.command, self.path, body))
        if self.headers.get('Authorization') != 'Bearer ' + TOKEN:
            return self.answer(401, {'error': 'a device token is needed'})
        if mode['v'] == '429' and mode['n429'] < 1:
            mode['n429'] += 1
            return self.answer(429, {'error': 'too many requests'})
        if mode['v'] == 'always429':
            return self.answer(429, {'error': 'too many requests'})
        if mode['v'] == 'redirect':
            self.send_response(302); self.send_header('Location', 'http://127.0.0.1:1/x'); self.end_headers(); return
        if mode['v'] == 'junk':
            return self.answer(200, None, b'not json')
        if mode['v'] == 'huge':
            return self.answer(200, None, b'{"text":"' + b'a' * 400000 + b'"}')
        if self.path == '/api/health':
            return self.answer(200, {'ok': True})
        if self.path == '/api/recall':
            q = json.loads(body)['query']
            if q == 'nothing':
                return self.answer(200, {'rang': False, 'hits': []})
            return self.answer(200, {'rang': q != 'weak', 'hits': [
                {'name': 'deploys-need-a-word', 'type': 'preference', 'abstract': 'No deploy\nwithout \x1b[2Jhis word.', 'strong': q != 'weak'}]})
        if self.path == '/api/note?name=deploys-need-a-word':
            return self.answer(200, {'name': 'deploys-need-a-word', 'type': 'preference', 'updated': '2026-10-13', 'abstract': 'short', 'body': 'the body\x07 text'})
        if self.path.startswith('/api/note'):
            return self.answer(404, {'error': 'no such note'})
        if self.path == '/api/brief?project=kimera':
            return self.answer(200, {'text': '- a: b'})
        return self.answer(403, {'error': 'not for a device'})
    do_GET = do_POST = handle_any


srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Door)
threading.Thread(target=srv.serve_forever, daemon=True).start()
tmp = tempfile.mkdtemp()
tok, conf = os.path.join(tmp, 'token'), os.path.join(tmp, 'seat.json')


def setup(port=None, token=TOKEN, perm=0o600, with_port=True):
    with open(tok, 'w') as f: f.write(token + '\n')
    os.chmod(tok, perm)
    row = {'memory_token_file': tok}
    if with_port: row['memory_port'] = port or srv.server_address[1]
    json.dump(row, open(conf, 'w'))


def run(*a, env=None):
    e = dict(os.environ, KIMERA_SEAT_CONF=conf, http_proxy='http://127.0.0.1:1', HTTP_PROXY='http://127.0.0.1:1')
    e.update(env or {})
    r = subprocess.run([sys.executable, os.path.join(HERE, 'kimera-memory')] + list(a), capture_output=True, text=True, env=e, timeout=60)
    return r.returncode, r.stdout, r.stderr


def check(name, ok):
    global fails
    print(('ok   ' if ok else 'FAIL ') + name)
    fails += 0 if ok else 1


setup()
c, o, e = run('health'); check('health answers through the door, and a proxy in the environment is not used', c == 0 and 'answers' in o)
c, o, e = run('recall', 'deploys', 'word')
check('recall prints the hit on one line', c == 0 and o.startswith('deploys-need-a-word  [preference, strong]  No deploy without'))
check('recall sends the words as one query', json.loads(seen[-1][2]) == {'query': 'deploys word'} and seen[-1][:2] == ('POST', '/api/recall'))
check('a screen-control character in a note never reaches the screen', '\x1b' not in o and 'silent' not in o)
c, o, e = run('recall', 'weak'); check('a weak hit is listed and the last line is silent', c == 0 and o.strip().splitlines()[-1] == 'silent' and 'deploys' in o)
c, o, e = run('recall', 'nothing'); check('no hit at all is just silent', c == 0 and o.strip() == 'silent')
c, o, e = run('read', 'deploys-need-a-word'); check('read prints the note', c == 0 and 'the body  text' in o and '\x07' not in o)
c, o, e = run('read', 'private-note'); check('a note that may not travel is "no such note", exit 1', c == 1 and 'no such note' in e and o == '')
c, o, e = run('brief', 'kimera'); check('brief prints the block', c == 0 and o.strip() == '- a: b')
n = len(seen)
for bad in (['read', '../x'], ['read', 'a b'], ['read', 'a?name=b'], ['brief', 'a/b'], ['recall'], ['recall', 'x' * 2500], ['write', 'x'], ['read', 'a', 'b'], []):
    c, o, e = run(*bad); check('bad arguments are refused before anything is sent: %s' % ' '.join(bad)[:30], c == 4 and len(seen) == n)
mode.update(v='429', n429=0); c, o, e = run('health'); check('one "too many requests" is waited out and tried again', c == 0)
mode.update(v='always429'); c, o, e = run('health'); check('a second one is said plainly, exit 1', c == 1 and 'too many' in e)
mode.update(v='redirect'); c, o, e = run('health'); check('a redirect is not followed (the token goes nowhere else)', c == 1)
mode.update(v='junk'); c, o, e = run('health'); check('an unreadable answer is exit 1', c == 1)
mode.update(v='huge'); c, o, e = run('brief', 'kimera'); check('an answer that is too long is refused', c == 1 and 'too long' in e)
mode.update(v='ok')
setup(token='W' * 44); c, o, e = run('health'); check('a wrong token: the door does not know this device, exit 1', c == 1 and 'does not know' in e)
check('the token is never printed', TOKEN not in o + e and 'W' * 44 not in o + e)
n = len(seen)
setup(perm=0o644); c, o, e = run('health'); check('a token file others can read is refused, nothing sent', c == 3 and len(seen) == n)
setup(token='short'); c, o, e = run('health'); check('a file that holds no token is refused, nothing sent', c == 3 and len(seen) == n)
setup(token='A' * 30 + '\r\nX-Evil: 1'); c, o, e = run('health'); check('a token with a line break in it is refused, nothing sent', c == 3 and len(seen) == n)
setup(with_port=False); c, o, e = run('health'); check('a device with no memory road says so, exit 3', c == 3 and 'no road' in e)
setup(port=80); c, o, e = run('health'); check('a port below 1024 is refused', c == 3)
setup(); os.remove(tok); c, o, e = run('health'); check('no token yet, exit 3', c == 3 and 'no token' in e)
# the listener must be this user's own: the client is loaded as a module and shown a table where another user holds the port
import importlib.machinery, importlib.util
ld = importlib.machinery.SourceFileLoader('kmem', os.path.join(HERE, 'kimera-memory'))
M = importlib.util.module_from_spec(importlib.util.spec_from_loader('kmem', ld)); ld.exec_module(M)
port = srv.server_address[1]
check('the pretend door, held by this user, counts as ours', M.ours(port))
head = 'sl local rem st tx rx tr tm retr uid\n'
def table(*rows):
    p = os.path.join(tmp, 'tcp'); open(p, 'w').write(head + ''.join('0: %s 00000000:0000 %s 0 0 0 0 0 %d 0 0\n' % r for r in rows)); M.PROC = p
table(('0100007F:%04X' % port, '0A', os.getuid() + 1)); check('a listener of another user is not ours', not M.ours(port))
table(('0100007F:%04X' % port, '0A', os.getuid()), ('00000000:%04X' % port, '0A', os.getuid() + 1)); check('one of ours and one of another user is not ours', not M.ours(port))
table(('0100007F:%04X' % port, '01', os.getuid())); check('a connection that is not a listener does not count', not M.ours(port))
table(); check('nothing listening is not ours', not M.ours(port))
M.PROC = os.path.join(tmp, 'gone'); check('a table that cannot be read is not ours', not M.ours(port))
M.CONF = conf; setup(); n = len(seen); table(('0100007F:%04X' % port, '0A', os.getuid() + 1))
try: M.ask('/api/health'); rc = 0
except SystemExit as x: rc = x.code
check('with another user on the port nothing is sent, exit 3', rc == 3 and len(seen) == n)
setup(port=1); srv.shutdown()
setup(port=srv.server_address[1]); c, o, e = run('health'); check('the door away is exit 3', c == 3 and 'away' in e)
print('%d failure(s)' % fails)
sys.exit(1 if fails else 0)
