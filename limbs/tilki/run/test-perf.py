#!/usr/bin/env python3
"""Hermetic checks for kimera-perf: a temp HOME and a fake kimera-run beside a copy of the program. No device, no network."""
import json, os, shutil, stat, subprocess, sys, tempfile

here = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp()
shutil.copy(os.path.join(here, 'kimera-perf'), tmp)
fake = os.path.join(tmp, 'kimera-run')
state = os.path.join(tmp, '.local/state/kimera')
fails = []


def check(label, cond):
    print(('ok   ' if cond else 'FAIL ') + label)
    if not cond:
        fails.append(label)


def run(out, code, dev='caretta'):
    open(fake, 'w').write('#!/bin/sh\ncat <<\'X\'\n%s\nX\nexit %d\n' % (out, code))
    os.chmod(fake, 0o755)
    r = subprocess.run([sys.executable, os.path.join(tmp, 'kimera-perf'), dev], env=dict(os.environ, HOME=tmp),
                       capture_output=True, text=True)
    p = os.path.join(state, 'now-%s.json' % dev)
    return r, (json.load(open(p)) if os.path.exists(p) else None)


GOOD = '{"t": 1, "avail_mb": 3000, "load1": 0.25, "swap_used_mb": 10, "temp_c": 50, "chats": {}}'
r, d = run(GOOD, 0)
check('an idle device still gives a latest reading', d and d['state'] == 'up' and d['avail_mb'] == 3000 and d['chats'] == {})
check('the latest reading is for this user only', stat.S_IMODE(os.stat(os.path.join(state, 'now-caretta.json')).st_mode) == 0o600)
check('the clock is ours, not the device\'s', d['t'] > 1000000000)
check('no record line while no chat runs', not os.path.exists(os.path.join(state, 'perf-caretta.tsv')))
r, d = run(GOOD.replace('{}}', '{"aiden-abcdef12": 250}}'), 0)
tsv = open(os.path.join(state, 'perf-caretta.tsv')).read().splitlines()
check('a chat gives a record line and a latest reading', len(tsv) == 2 and 'aiden-abcdef12=250' in tsv[1] and d['chats'] == {'aiden-abcdef12': 250})
r, d = run('device away', 3)
check('a device that does not answer reads as away', d == dict(device='caretta', t=d['t'], state='away'))
r, d = run('refused', 2)
check('a refusal reads as unknown', d['state'] == 'unknown' and 'avail_mb' not in d)
for bad in ('not json', '{"avail_mb": "3000\\n", "load1": 0, "swap_used_mb": 0, "temp_c": 1, "chats": {}}',
            GOOD.replace('{}}', '{"evil\\tname": 1}}'), GOOD.replace('3000', '-5'), '[1]'):
    r, d = run(bad, 0)
    check('malformed answer reads as unknown: %s' % bad[:28], d['state'] == 'unknown' and 'chats' not in d)
check('a malformed answer added no record line', len(open(os.path.join(state, 'perf-caretta.tsv')).read().splitlines()) == 2)
r, d = run(GOOD, 0)
os.remove(fake)
r = subprocess.run([sys.executable, os.path.join(tmp, 'kimera-perf'), 'caretta'], env=dict(os.environ, HOME=tmp), capture_output=True, text=True)
d = json.load(open(os.path.join(state, 'now-caretta.json')))
check('a door that cannot be run replaces an old "up" with unknown', d['state'] == 'unknown' and r.returncode == 1)
r, d = run(GOOD, 0, dev='../x')
check('a device name with a path in it is refused', r.returncode != 0 and not os.path.exists(os.path.join(tmp, '.local/state/x.json')))
print('\n%d failure(s)' % len(fails))
sys.exit(1 if fails else 0)
