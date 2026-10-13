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
check('seed leaves no spool file behind', not [f for f in os.listdir(os.path.join(tmp, 'kimera')) if f.startswith('seed.')])
check('seed is in the audit log', 'seeded' in open(S.LOG).read())

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
