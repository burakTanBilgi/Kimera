#!/usr/bin/env python3
"""Hermetic checks for kimera-seat: temp HOME, a fake `tmux` that records argv. No device, no network."""
import importlib.machinery, importlib.util, io, json, os, stat, subprocess, sys, tempfile

tmp = tempfile.mkdtemp()
os.environ['HOME'] = tmp
bindir = os.path.join(tmp, 'bin'); os.makedirs(bindir)
rec = os.path.join(tmp, 'tmux.log')
sess = os.path.join(tmp, 'sessions')
open(sess, 'w').close()
shim = os.path.join(bindir, 'tmux')
open(shim, 'w').write(f'''#!/bin/sh
echo "$@" >> {rec}
shift 2
case "$1" in
  list-sessions) cat {sess};;
  new-session) while [ $# -gt 0 ]; do if [ "$1" = -s ]; then echo "$2" >> {sess}; break; fi; shift; done;;
  has-session) grep -q "^$(echo "$3" | tr -d =:)$" {sess};;
esac
exit 0
''')
os.chmod(shim, 0o755)
os.environ['PATH'] = bindir + ':' + os.environ['PATH']
seatdir = os.path.join(tmp, '.config/kimera/seat'); os.makedirs(seatdir)
root = os.path.join(tmp, 'seats'); os.makedirs(root)
open(seatdir + '/settings.pristine.json', 'w').write('{"enabledPlugins":{}}')
json.dump({'chat': True, 'seat_roots': [root], 'config_dir': tmp, 'claude': '/bin/claude', 'hook_port': 8732,
           'hook_token_file': tmp + '/tok', 'limits': {'avail_mb': 1, 'disk_gb': 0, 'max_chats': 1}},
          open(seatdir + '/seat.json', 'w'))
ld = importlib.machinery.SourceFileLoader('seat', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kimera-seat'))
spec = importlib.util.spec_from_loader('seat', ld); S = importlib.util.module_from_spec(spec); ld.exec_module(S)
S.snapshot = lambda: dict(avail_mb=4000, load1=0.1, cores=4, disk_gb=50, temp_c=40, heavy=0, chats=len(S.sessions()))

fails = []
def check(label, cond):
    print(('ok   ' if cond else 'FAIL ') + label)
    if not cond: fails.append(label)
def call(cmd, data=b''):
    os.environ['SSH_ORIGINAL_COMMAND'] = cmd
    out = io.StringIO(); so = sys.stdout; sys.stdout = out
    class Raw:  # the program writes bytes for capture and fetch
        write = staticmethod(lambda b: out.write(b.decode('utf-8', 'replace')))
    out.buffer = Raw
    try:
        class In: buffer = io.BytesIO(data)
        si = sys.stdin; sys.stdin = In
        rc = S.main()
    finally:
        sys.stdout = so; sys.stdin = si
    return rc, out.getvalue().strip()

sid = '7b552902-c141-45d5-9430-0bef261feac2'
N = 'aiden-abcdef12'
check('admit ok', call('admit') == (0, 'ok'))
check('bad name', call('has Bad')[0] == 4)
S_NAME_OK = bool(S.NAME_RE.fullmatch('aiden-abcdef12')) and not S.NAME_RE.fullmatch('aiden-abcdef12\n')
check('trailing newline is not a name', S_NAME_OK and not S.SID_RE.fullmatch(sid + '\n') and not S.PATH_RE.fullmatch(root + '\n'))
check('bad verb', call('rm -rf /')[0] == 4)
check('empty', call('')[0] == 4)
check('cwd outside root refused', call(f'start {N} /etc {sid}')[0] == 2)
check('cwd dotdot bad', call(f'start {N} {root}/../x {sid}')[0] == 4)
check('cwd space bad', call(f'start {N} {root}/a b {sid}')[0] == 4)
check('bad sid', call(f'start {N} {root}/a nope')[0] == 4)
check('unknown option', call(f'start {N} {root}/a {sid} bypass')[0] == 4)
rc, out = call(f'start {N} {root}/a {sid} plan sonnet Read,Grep,Glob,Bash')
check('start ok', (rc, out) == (0, 'ok'))
log = open(rec).read()
check('a chat does not update the program under itself', '-e DISABLE_AUTOUPDATER=1' in log)
check('claude argv', f'--session-id {sid} --permission-mode plan --model sonnet --setting-sources user --settings {seatdir}/settings.json --tools Read,Grep,Glob,Bash --strict-mcp-config --mcp-config {{"mcpServers":{{}}}}' in log)
check('hook env passed', 'AIDEN_HOOK_URL=http://127.0.0.1:8732/hook' in log and 'CLAUDE_CONFIG_DIR=' + tmp in log)
check('folder made 0700', stat.S_IMODE(os.stat(root + '/a').st_mode) == 0o700)
open(tmp + '/settings.json', 'w').write('{"permissions":{"allow":["Bash"]}}')
check('user settings with permissions refuse a start', call(f'start aiden-third0001 {root}/c {sid}')[0] == 2)
os.remove(tmp + '/settings.json')
open(seatdir + '/settings.pristine.json', 'w').write('{"enabledPlugins":{}}')
open(seatdir + '/settings.json', 'w').write('{"permissions":{"defaultMode":"bypassPermissions"}}')
S.sessions = lambda: []
call(f'start aiden-fourth0001 {root}/d {sid}')
check('tampered seat settings restored at start', open(seatdir + '/settings.json').read() == '{"enabledPlugins":{}}')
S.sessions = lambda: ['aiden-abcdef12']
check('second chat refused (limit 1)', call(f'start aiden-other0001 {root}/b {sid}')[0] == 2)
check('key bad', call(f'key {N} Delete')[0] == 4)
check('type too long', call(f'type {N}', b'a' * (S.MAX_TYPE + 1))[0] == 2)
check('type ok', call(f'type {N}', b'hello')[0] == 0)
check('audit lines', all(w in open(S.LOG).read() for w in ('start', 'type', 'refused', 'bad')))
check('type logs length only', 'len=5' in open(S.LOG).read() and 'hello' not in open(S.LOG).read())
check('no such chat', call('kill aiden-nothere01') [0] == 2)
# seed: a read copy of the work arrives as a tar
import io as _io, tarfile as _tar
def tar_of(entries):
    b = _io.BytesIO()
    with _tar.open(fileobj=b, mode='w') as t:
        for name, body, kind in entries:
            i = _tar.TarInfo(name)
            if kind == 'link':
                i.type, i.linkname = _tar.SYMTYPE, body
                t.addfile(i)
            else:
                i.size, i.mode = len(body), 0o755 if kind == 'exec' else 0o644
                t.addfile(i, _io.BytesIO(body))
    return b.getvalue()
C = 'a' * 40
S.sessions = lambda: []
open(sess, 'w').close()
work = root + '/team-seat'
rc, out = call(f'seed {work} {C}', tar_of([('README.md', b'hello', 'file'), ('src/run.sh', b'#!/bin/sh\n', 'exec'), ('ln', '/etc/passwd', 'link')]))
check('seed unpacks plain files and answers ok FILES BYTES COMMIT', (rc, out) == (0, f'ok 2 15 {C}'))
check('seed keeps the exec bit, private modes, and leaves links out',
      open(work + '/README.md').read() == 'hello' and stat.S_IMODE(os.stat(work + '/src/run.sh').st_mode) == 0o700
      and stat.S_IMODE(os.stat(work + '/README.md').st_mode) == 0o600 and not os.path.lexists(work + '/ln'))
rc, out = call(f'seed {work} {C}', tar_of([('only.txt', b'x', 'file')]))
check('seeding again replaces the folder whole', rc == 0 and os.listdir(work) == ['only.txt'])
for label, entries in (('a path that climbs out', [('../evil', b'x', 'file')]), ('an absolute path', [('/tmp/evil', b'x', 'file')])):
    rc, out = call(f'seed {work} {C}', tar_of(entries))
    check('seed refuses %s and keeps the old folder' % label, rc == 2 and os.listdir(work) == ['only.txt'])
check('seed refuses the escape itself', not os.path.exists(root + '/evil') and not os.path.exists('/tmp/evil'))
_big = _io.BytesIO()
with _tar.open(fileobj=_big, mode='w') as _t:
    for _i in range(7):
        _d = _tar.TarInfo('d%d' % _i); _d.type = _tar.DIRTYPE; _t.addfile(_d)
S.MAX_SEED_FILES = 2
check('seed counts entries as it reads them', call(f'seed {work} {C}', _big.getvalue())[0] == 2 and os.listdir(work) == ['only.txt'])
S.MAX_SEED_FILES = 20000
check('seed refuses what is not a tar', call(f'seed {work} {C}', b'not a tar at all')[0] == 2 and os.listdir(work) == ['only.txt'])
check('seed refuses a folder outside the roots', call(f'seed /etc/x {C}', tar_of([('a', b'x', 'file')]))[0] == 2)
check('seed refuses the seat root itself', call(f'seed {root} {C}', tar_of([('a', b'x', 'file')]))[0] == 2 and os.path.isdir(work))
check('seed needs a full commit id', call(f'seed {work} abc', tar_of([('a', b'x', 'file')]))[0] == 4)
S.MAX_SEED_FILES = 2
check('seed refuses too many files', call(f'seed {work} {C}', tar_of([('a', b'x', 'file'), ('b', b'x', 'file'), ('c', b'x', 'file')]))[0] == 2)
S.MAX_SEED_FILES = 20000
S.MAX_SEED = 10
check('seed refuses work over the size limit', call(f'seed {work} {C}', tar_of([('big', b'x' * 11, 'file')]))[0] == 2 and os.listdir(work) == ['only.txt'])
S.MAX_SEED = 200 << 20
open(sess, 'w').write('aiden-busy0001\t%s\n' % work)
check('seed is refused while a chat runs in that folder', call(f'seed {work} {C}', tar_of([('a', b'x', 'file')]))[0] == 2 and os.listdir(work) == ['only.txt'])
open(sess, 'w').close()
open(sess, 'w').write('aiden-busy0002\t%s\n' % root)
check('seed is refused under a folder a chat runs in', call(f'seed {work}/deeper {C}', tar_of([('a', b'x', 'file')]))[0] == 2)
open(sess, 'w').close()
_cfg = json.load(open(seatdir + '/seat.json'))
json.dump(dict(_cfg, limits=dict(_cfg['limits'], disk_gb=10 ** 6)), open(seatdir + '/seat.json', 'w'))
check('seed keeps the device\'s disk floor', call(f'seed {work} {C}', tar_of([('a', b'x', 'file')]))[0] == 2 and os.listdir(work) == ['only.txt'])
json.dump(dict(_cfg, chat=False, why_not='no chats here'), open(seatdir + '/seat.json', 'w'))
check('a device that takes no chats takes no work', call(f'seed {work} {C}', tar_of([('a', b'x', 'file')])) == (2, 'no chats here'))
json.dump(_cfg, open(seatdir + '/seat.json', 'w'))
os.symlink('/etc', work + '.seed-new')
rc, out = call(f'seed {work} {C}', tar_of([('fresh.txt', b'x', 'file')]))
check('a link planted where the work is built is not followed', rc == 0 and os.listdir(work) == ['fresh.txt'] and not os.path.exists('/etc/fresh.txt'))
call(f'seed {work} {C}', tar_of([('only.txt', b'x', 'file')]))
check('seed leaves no spool file behind', not [f for f in os.listdir(os.path.join(tmp, 'kimera')) if f.startswith('seed.')])
check('seed is in the audit log', 'seeded' in open(S.LOG).read())

# fetch: what a chat changed in a seeded folder comes back as a text diff
back = root + '/builder'
call(f'seed {back} {C}', tar_of([('a.txt', b'one\ntwo\n', 'file'), ('.gitignore', b'target/\n', 'file')]))
check('fetch says no changes right after a seed', call(f'fetch {back}') == (1, 'no changes'))
open(back + '/a.txt', 'w').write('one\n2\n'); open(back + '/new.txt', 'w').write('fresh\n')
os.makedirs(back + '/target'); open(back + '/target/big.o', 'wb').write(b'\0' * 100)
rc, out = call(f'fetch {back}')
check('fetch gives the edit and the new file as one diff', rc == 0 and '-two' in out and '+2' in out and '+++ b/new.txt' in out and '+fresh' in out)
check('fetch leaves out what the work itself ignores', 'target' not in out)
p0 = subprocess.run(['git', 'init', '-q', tmp + '/apply'], capture_output=True)
open(tmp + '/apply/a.txt', 'w').write('one\ntwo\n')
ap = subprocess.run(['git', '-C', tmp + '/apply', 'apply', '--check', '-'], input=out + '\n', capture_output=True, text=True)
check('the diff applies with git apply --check', ap.returncode == 0)
os.symlink('/etc/passwd', back + '/ln')
rc, out = call(f'fetch {back}')
check('fetch refuses a link by name', rc == 2 and 'ln' in out)
os.remove(back + '/ln'); open(back + '/pic.bin', 'wb').write(bytes(range(256)) * 4)
rc, out = call(f'fetch {back}')
check('fetch refuses a binary file by name', rc == 2 and 'pic.bin' in out)
os.remove(back + '/pic.bin'); S.MAX_FETCH = 20
check('fetch refuses changes over the size limit', call(f'fetch {back}')[0] == 2)
S.MAX_FETCH = 2 << 20
open(back + '/.gitattributes', 'w').write('*.bin diff text\n'); open(back + '/pic.bin', 'wb').write(bytes(range(256)) * 4)
rc, out = call(f'fetch {back}')
check('a chat\'s own .gitattributes cannot pass a binary file off as text', rc == 2 and '\x00' not in out)
os.remove(back + '/pic.bin'); os.remove(back + '/.gitattributes')
evil = back + '/x\n2026-01-01T00:00:00+0000 start aiden-forged001 ok'
os.symlink('/etc/passwd', evil)
rc, out = call(f'fetch {back}')
check('a file name cannot forge a line of the answer or of the log', rc == 2 and len(out.splitlines()) == 1
      and not any(l.startswith('2026-01-01T00:00:00+0000 start aiden-forged001') for l in open(S.LOG).read().splitlines()))
os.remove(evil)
open(back + '/esc.txt', 'w').write('hello \x1b[2J\x1b]0;owned\x07 there\n')
rc, out = call(f'fetch {back}')
check('changes with terminal control characters do not travel', rc == 2 and '\x1b' not in out)
os.remove(back + '/esc.txt')
for label, body in (('a direction override', 'if admin\u202e // ok\n'), ('a lone carriage return', 'safe\rrm -rf\n'), ('a zero-width space', 'a\u200bb\n'), ('an invisible tag character', 'a\U000E0041b\n'),
                    ('a soft hyphen', 'pass\u00adword\n'), ('a hidden variation selector', 'a\U000E0101b\n'), ('a private-use character', 'a\ue000b\n'), ('a Hangul filler', 'a\u3164b\n'),
                    ('a no-break space', 'a\u00a0b\n'), ('a blank braille cell', 'a\u2800b\n'), ('an emoji variation selector', 'a\ufe0fb\n'),
                    ('a combining grapheme joiner', 'a\u034fb\n')):
    open(back + '/h.txt', 'w', newline='').write(body)
    check('changes with %s do not travel' % label, call(f'fetch {back}')[0] == 2)
os.remove(back + '/h.txt')
open(back + '/crlf.txt', 'w', newline='').write('one\r\ntwo\r\n')
check('a file with Windows line ends still travels', call(f'fetch {back}')[0] == 0)
open(back + '/crlf.txt', 'w', newline='').write('T\u00fcrk\u00e7e \u2764 \U0001F600 \u4e2d\u6587 caf\u00e9\r\n')
check('ordinary non-English text and emoji still travel', call(f'fetch {back}')[0] == 0)
os.remove(back + '/crlf.txt')
open(os.path.join(S.base_of(os.path.realpath(back)), 'index.lock'), 'w').close()
open(back + '/after.txt', 'w').write('fine\n')
rc, out = call(f'fetch {back}')
check('a lock left by a fetch that was cut short does not block the next one', rc == 0 and '+fine' in out)
os.remove(back + '/after.txt')
odd = os.fsencode(back) + b'/caf\xe9.txt'
open(odd, 'wb').write(b'x' * (3 << 20))
rc, out = call(f'fetch {back}')
check('a name that is not UTF-8 does not slip past the size limit', rc == 2 and 'too large' in out)
os.remove(odd)
seeds = os.path.join(tmp, 'kimera', 'seeds')
size = lambda: sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(seeds) for f in fs)
before = size(); open(back + '/huge.txt', 'w').write('x' * (3 << 20))
rc, out = call(f'fetch {back}')
check('a huge file is refused by name before anything is taken in', rc == 2 and 'huge.txt' in out and size() - before < (1 << 20))
os.remove(back + '/huge.txt')
os.makedirs(root + '/never'); check('fetch refuses a folder that was not seeded', call(f'fetch {root}/never')[0] == 2)
check('fetch refuses a folder outside the roots', call('fetch /etc')[0] == 2)
check('the record of the seed is kept outside the seat folder', not os.path.exists(back + '/.git') and os.listdir(os.path.join(tmp, 'kimera', 'seeds')))
call(f'seed {back} {C}', tar_of([('a.txt', b'one\ntwo\n', 'file')]))
check('seeding again starts the comparison afresh', call(f'fetch {back}') == (1, 'no changes'))

# a device with a mode allow-list, a memory box and a private tmux (Kirpi's shape)
S.sessions = lambda: []
cfg = json.load(open(seatdir + '/seat.json'))
priv = os.path.join(tmp, 'kimera/tmux/root/usr/bin'); os.makedirs(priv)
import shutil; shutil.copy(shim, priv + '/tmux')
import hashlib
S.TMUX_SHA256 = hashlib.sha256(open(priv + '/tmux', 'rb').read()).hexdigest()
cfg.update(modes=['plan'], box_mb=500, tmux=True, tools_force='Read,Grep,Glob', node=True)
json.dump(cfg, open(seatdir + '/seat.json', 'w'))
open(rec, 'w').close()
sid2 = '8c663a13-d252-46e6-a541-1cfa02f0bfd3'
check('mode outside the allow-list refused', call(f'start aiden-boxed0001 {root}/e {sid2} auto')[0] == 2)
check('no mode refused when a list is set', call(f'start aiden-boxed0001 {root}/e {sid2}')[0] == 2)
rc, out = call(f'start aiden-boxed0001 {root}/e {sid2} plan sonnet Read,Grep,Glob,Bash')
log2 = open(rec).read()
check('device narrows the tools', '--tools Read,Grep,Glob ' in log2 and 'Bash' not in log2.split('new-session')[-1])
check('the private Node is first on the chat\'s PATH', '-- env PATH=%s/kimera/node/bin:' % tmp in log2 and 'PATH=' not in log)
check('plan mode starts, boxed', rc == 0 and 'systemd-run --user --scope --quiet --collect -p MemoryMax=500M -p MemorySwapMax=0 -- env PATH=' in log2 and ' /bin/claude --session-id' in log2)
S.TMUX_SHA256 = '0' * 64  # a swapped binary is refused, never executed
check('a private tmux that is not the expected package is refused', call('has aiden-abcdef12')[0] == 2)
print('\n%d failure(s)' % len(fails))
sys.exit(1 if fails else 0)
