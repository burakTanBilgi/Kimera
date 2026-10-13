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
check('tampered seat settings restored at start', json.load(open(seatdir + '/settings.json')) == {'enabledPlugins': {}})
os.makedirs(tmp + '/plugins/synced/org1/p1/.claude-plugin'); json.dump({'name': 'guardish'}, open(tmp + '/plugins/synced/org1/p1/.claude-plugin/plugin.json', 'w'))
json.dump({'pluginUsage': {'nagger@synced': {}, 'cc-builtin@builtin': {}}}, open(tmp + '/.claude.json', 'w'))
S.sessions = lambda: []
call(f'start aiden-fifth00001 {root}/e5 {sid}')
check('the chat keeps its own name whatever plugins are found', '-s aiden-fifth00001 ' in open(rec).read().splitlines()[-1] or any('-s aiden-fifth00001 ' in l for l in open(rec).read().splitlines()))
check('every organization plugin that could load is off at each start', json.load(open(seatdir + '/settings.json'))['enabledPlugins'] == {'guardish@synced': False, 'nagger@synced': False})
json.dump({'pluginUsage': {'bad name!@synced': {}}}, open(tmp + '/.claude.json', 'w'))
check('a plugin whose name cannot be switched off refuses the start', call(f'start aiden-sixth00001 {root}/e6 {sid}')[0] == 2)
os.remove(tmp + '/.claude.json'); open(tmp + '/plugins/synced/org1/p1/.claude-plugin/plugin.json', 'w').write('{broken')
check('a plugin that cannot be read refuses the start', call(f'start aiden-sixth00001 {root}/e6 {sid}')[0] == 2)
__import__('shutil').rmtree(tmp + '/plugins')
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

# the memory pack: a second tar in the same stream, laid read-only, never reported by fetch
def pack_of(entries):
    b = _io.BytesIO()
    with _tar.open(fileobj=b, mode='w') as t:
        for name, body in entries:
            i = _tar.TarInfo('.memory/' + name); i.size, i.mode = len(body), 0o444
            t.addfile(i, _io.BytesIO(body))
    return b.getvalue()
mem = root + '/with-memory'
rc, out = call(f'seed {mem} {C}', tar_of([('code.txt', b'x\n', 'file')]) + pack_of([('INDEX.md', b'# what Tan decided\n'), ('notes/a.md', b'a\n')]))
check('a memory pack sent after the work lands in .memory/', rc == 0 and out.startswith('ok 3 ') and open(mem + '/.memory/INDEX.md').read().startswith('# what'))
check('the memory pack is read-only and the work is not', stat.S_IMODE(os.stat(mem + '/.memory/notes/a.md').st_mode) == 0o400 and stat.S_IMODE(os.stat(mem + '/code.txt').st_mode) == 0o600)
check('work that carries its own .memory is refused by the device too', call(f'seed {mem} {C}', tar_of([('.memory/INDEX.md', b'planted\n', 'file')]))[0] == 2
      and call(f'seed {mem} {C}', tar_of([('.Memory/INDEX.md', b'planted\n', 'file')]))[0] == 2 and open(mem + '/.memory/INDEX.md').read().startswith('# what'))
check('fetch does not report the memory pack', call(f'fetch {mem}') == (1, 'no changes'))

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

# pull: one finished file comes out of a seat folder, by folder handle, never through a link
built = root + '/build'; os.makedirs(built + '/target/release')
open(built + '/target/release/prog', 'wb').write(b'\x7fELF' + bytes(range(256)))
rc, out = call(f'pull {built} target/release/prog')
check('pull sends the bytes of one file', rc == 0 and len(out.encode('utf-8', 'replace')) > 100 and 'ELF' in out)
check('pull is in the audit log', 'pulled' in open(S.LOG).read() and 'file=target/release/prog' in open(S.LOG).read())
os.symlink('/etc/passwd', built + '/target/release/leak'); os.symlink('/etc', built + '/target/etc')
check('pull refuses a link to a file', call(f'pull {built} target/release/leak')[0] == 2)
check('pull refuses a path through a linked folder', call(f'pull {built} target/etc/passwd')[0] == 2)
check('pull refuses a step upward', call(f'pull {built} ../a.txt')[0] == 4 and call(f'pull {built} target/../../x')[0] == 4)
check('pull refuses a folder', call(f'pull {built} target/release')[0] == 2)
check('pull refuses a missing file', call(f'pull {built} target/release/nope')[0] == 2)
check('pull refuses a folder outside the roots', call('pull /etc passwd')[0] == 2)
S.MAX_PULL = 10
check('pull refuses a file over the limit', call(f'pull {built} target/release/prog')[0] == 2)
S.MAX_PULL = 64 << 20
other = os.path.join(tmp, 'elsewhere'); os.makedirs(other); open(other + '/tool', 'w').write('x')
check('a build folder outside the seat roots is refused unless the row names it', call(f'pull {other} tool')[0] == 2)
_c = json.load(open(seatdir + '/seat.json')); json.dump(dict(_c, pull_roots=[other]), open(seatdir + '/seat.json', 'w'))
check('a build folder the row names may be pulled from, and only pulled from', call(f'pull {other} tool') == (0, 'x') and call(f'seed {other}/s {C}', tar_of([('a', b'x', 'file')]))[0] == 2)
json.dump(_c, open(seatdir + '/seat.json', 'w'))

# a device with a mode allow-list, a memory box and a private tmux (Kirpi's shape)
S.sessions = lambda: []
cfg = json.load(open(seatdir + '/seat.json'))
priv = os.path.join(tmp, 'kimera/tmux/root/usr/bin'); os.makedirs(priv)
import shutil; shutil.copy(shim, priv + '/tmux')
import hashlib
S.TMUX_SHA256 = hashlib.sha256(open(priv + '/tmux', 'rb').read()).hexdigest()
os.makedirs(tmp + '/kimera/node/bin', exist_ok=True); os.makedirs(tmp + '/.cargo/bin', exist_ok=True)
cfg.update(modes=['plan'], box_mb=500, tmux=True, tools_force='Read,Grep,Glob', node=True)
json.dump(cfg, open(seatdir + '/seat.json', 'w'))
open(rec, 'w').close()
sid2 = '8c663a13-d252-46e6-a541-1cfa02f0bfd3'
check('mode outside the allow-list refused', call(f'start aiden-boxed0001 {root}/e {sid2} auto')[0] == 2)
check('no mode refused when a list is set', call(f'start aiden-boxed0001 {root}/e {sid2}')[0] == 2)
rc, out = call(f'start aiden-boxed0001 {root}/e {sid2} plan sonnet Read,Grep,Glob,Bash')
log2 = open(rec).read()
check('device narrows the tools', '--tools Read,Grep,Glob ' in log2 and 'Bash' not in log2.split('new-session')[-1])
check('the private Node and the Rust tools are last on the chat\'s PATH, never first', (':%s/kimera/node/bin:%s/.cargo/bin ' % (tmp, tmp)) in log2 and '-- env PATH=%s/kimera' % tmp not in log2 and '-- env PATH=%s/.cargo' % tmp not in log2 and 'PATH=' not in log)
check('plan mode starts, boxed', rc == 0 and 'systemd-run --user --scope --quiet --collect -p MemoryMax=500M -p MemorySwapMax=0 -- env PATH=' in log2 and ' /bin/claude --session-id' in log2)
# the working class: a mode that can write parks the local model through a lease and gets the bigger box
joblog = os.path.join(tmp, 'job.log'); fakejob = os.path.join(tmp, 'kimera/bin/kimera-job')
os.makedirs(os.path.dirname(fakejob), exist_ok=True)
open(fakejob, 'w').write(f"""#!/bin/sh
echo "$@" >> {joblog}
cat {tmp}/job-$1.json 2>/dev/null || echo '{{"ok": true}}'
""")
os.chmod(fakejob, 0o755)
def answer(cmd, obj): json.dump(obj, open(f'{tmp}/job-{cmd}.json', 'w'))
answer('lease', {'ok': True, 'token': 'abc123'}); answer('status', {'state': 'ready', 'job': 'text', 'lease': None, 'busy': False, 'waiting': 0})
cfg.update(working={'box_mb': 1800, 'avail_mb': 2300, 'frees_mb': 2000, 'hold_minutes': 120}, card='You are on a small test machine with 4 cores.')
json.dump(cfg, open(seatdir + '/seat.json', 'w'))
S.sessions = lambda: []; open(sess, 'w').close(); open(rec, 'w').close()
sid3 = '9d774b24-e363-47f7-b652-2d0b13f1c0e4'
rc, out = call(f'start aiden-work0001 {root}/w {sid3} auto sonnet Read,Grep,Glob,Bash,Edit,Write')
log3 = open(rec).read(); jl = open(joblog).read()
check('a mode that can write starts the working class through a lease', rc == 0 and 'lease chat --minutes 120 --holder aiden-work0001' in jl)
check('the working chat gets the bigger box and its own tools', 'MemoryMax=1800M' in log3 and '--tools Read,Grep,Glob,Bash,Edit,Write' in log3)
check('the working chat is told about the machine and its limits', '--append-system-prompt You are on a small test machine with 4 cores. This chat may edit' in log3 and '1800 MB of memory' in log3 and '120 minutes' in log3)
S.sessions = lambda: ['aiden-work0001']
call('kill aiden-work0001')
check('stopping a working chat gives the machine back', 'chat-end aiden-work0001' in open(joblog).read())
S.sessions = lambda: []; open(rec, 'w').close(); open(joblog, 'w').close()
rc, out = call(f'start aiden-lite00001 {root}/l {sid3} plan sonnet')
log3 = open(rec).read()
check('plan mode is still the light class: small box, read tools, no lease', rc == 0 and 'MemoryMax=500M' in log3 and '--tools Read,Grep,Glob ' in log3 and 'lease' not in open(joblog).read())
check('the light chat is told it only reads', 'This chat only reads' in log3 and '500 MB' in log3)
answer('lease', {'ok': False, 'error': 'the local model is working; ask again in a moment'}); open(rec, 'w').close()
rc, out = call(f'start aiden-work0002 {root}/w {sid3} auto')
check('a refused lease refuses the start with its sentence', rc == 2 and 'the local model is working' in out and 'new-session' not in open(rec).read())
answer('lease', {'ok': True, 'token': 'abc123'}); open(joblog, 'w').close()
S.snapshot = lambda: dict(avail_mb=900, load1=0.1, cores=4, disk_gb=50, temp_c=40, heavy=0, chats=0)
rc, out = call(f'start aiden-work0003 {root}/w {sid3} auto')
check('a working start that does not fit gives the machine back', rc == 2 and 'memory' in out and 'chat-end aiden-work0003' in open(joblog).read())
check('takes: working when parking the model would make room', json.loads(call('sample')[1])['takes'] == 'working')
answer('status', {'state': 'ready', 'job': 'text', 'lease': None, 'busy': False, 'waiting': 2})
check('takes: light when the model is owed a turn', json.loads(call('sample')[1])['takes'] == 'light')
S.snapshot = lambda: dict(avail_mb=300, load1=0.1, cores=4, disk_gb=50, temp_c=90, heavy=0, chats=0)
check('takes: none when nothing fits', json.loads(call('sample')[1])['takes'] == 'none')
S.snapshot = lambda: dict(avail_mb=4000, load1=0.1, cores=4, disk_gb=50, temp_c=40, heavy=0, chats=len(S.sessions()))
S.TMUX_SHA256 = '0' * 64  # a swapped binary is refused, never executed
check('a private tmux that is not the expected package is refused', call('has aiden-abcdef12')[0] == 2)
print('\n%d failure(s)' % len(fails))
sys.exit(1 if fails else 0)
