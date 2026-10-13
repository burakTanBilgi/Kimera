#!/usr/bin/env python3
"""test-sim: kimera-job v2 against a simulated Kirpi (fake systemd, fake clock-free logic), run on Tilki.
Covers what test-switch.sh (which needs the real machine) does not: on-demand mode, wake, the park marker,
the agent lease, crash versus park, a stale idle clock. Usage: python3 test-sim.py   Exit 0 when all pass."""
import contextlib, importlib.machinery, importlib.util, io, json, os, sys, tempfile, time

here = os.path.dirname(os.path.abspath(__file__))
l = importlib.machinery.SourceFileLoader('kj', os.path.join(here, 'kimera-job'))
m = importlib.util.module_from_spec(importlib.util.spec_from_loader('kj', l)); l.exec_module(m)
d = tempfile.mkdtemp()
m.RUN = d; m.LEASE, m.MARK, m.LOCK = (f'{d}/{n}' for n in ('lease.json', 'switching.json', 'lock'))
m.ACTIVITY, m.WOKE, m.PARKED = (f'{d}/{n}.json' for n in ('activity', 'woke', 'parked'))
m.LOG = d + '/log'; m.SHOWN = d + '/shown'; m.ONDEMAND = d + '/ondemand'
MIND, EYES, SEARCH = 'kimera-mind.service', 'kimera-eyes.service', 'kimera-search.service'
up = {MIND: True, EYES: False, SEARCH: True}
class R: stdout = ''
def sysctl(*a):
    if a[0] == 'stop': up[a[1]] = False
    if a[0] == 'start':
        up[a[1]] = True
        if a[1] == MIND: up[EYES] = False
        if a[1] == EYES: up[MIND] = False
    r = R(); r.stdout = ('active' if up.get(a[1]) else 'inactive') if a[0] == 'is-active' else ''; return r
m.sysctl = sysctl
m.healthy = lambda b: (up[MIND] or up[EYES]) if b == m.TEXT_URL else up[SEARCH]
m.busy = lambda: False; m.hearing = lambda: False; m.wait_ready = lambda mode: m.mode_now() == mode
m.totals = lambda: 7.0
class Done: returncode = 0; stdout = ''; stderr = ''
m.subprocess.run = lambda *a, **k: Done()              # cmd_lease calls `systemd-run --user`: start no real timers from the sim
fails = []
def check(name, cond):
    print(('ok   ' if cond else 'FAIL ') + name); cond or fails.append(name)
def run(fn, *a):
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf): fn(*a)
    except SystemExit as e: return e.code, (json.loads(buf.getvalue()) if buf.getvalue() else {})
def age(seconds):                                     # pretend `seconds` have passed with no work
    for f in (m.WOKE, m.ACTIVITY):
        o = m.read(f)
        if o: o['at' if 'at' in o else 'changed'] -= seconds; m.write(f, o)
def reset(on=False, mind=True):
    up.update({MIND: mind, EYES: False, SEARCH: True})
    for f in (m.LEASE, m.PARKED, m.ACTIVITY, m.WOKE, m.ONDEMAND): m.drop(f)
    if on: open(m.ONDEMAND, 'w').close()

reset()                                                # A: resident, agent lease
c, o = run(m.cmd_lease, ['agent', '--minutes', '5', '--holder', 't']); tok = o['token']
check('A agent lease stops the model and search', not up[MIND] and not up[SEARCH] and c == 0)
c, o = run(m.cmd_wake, []); check('A wake is refused during the lease, with seconds_left', c == 2 and 'seconds_left' in o)
c, o = run(m.cmd_ensure); check('A ensure leaves the lease alone', o['did'] == [])
c, o = run(m.cmd_release, [tok]); check('A release brings text and search back', up[MIND] and up[SEARCH] and o['job'] == 'text')

reset(on=True)                                         # B: on-demand, agent lease then park and wake
c, o = run(m.cmd_lease, ['agent', '--minutes', '5', '--holder', 't']); tok = o['token']
c, o = run(m.cmd_release, [tok]); check('B release in on-demand mode stays parked and says so', not up[MIND] and o.get('parked') and o['job'] == 'none')
c, o = run(m.cmd_ensure); check('B ensure keeps a parked model parked', not up[MIND] and o['did'] == [])
c, o = run(m.cmd_wake, ['--holder', 'p']); check('B wake loads text and search', c == 0 and up[MIND] and up[SEARCH])
c, o = run(m.cmd_ensure); check('B ensure right after wake does not park', up[MIND] and o['did'] == [])
age(200); c, o = run(m.cmd_ensure); check('B ensure after 200 s idle parks it', not up[MIND] and os.path.exists(m.PARKED))
c, o = run(m.cmd_ensure); check('B ensure keeps it parked', not up[MIND])

reset(on=True, mind=False)                             # C: crashed, not parked (no marker)
c, o = run(m.cmd_ensure); check('C a model that is down without the park marker is restarted', up[MIND])

reset(on=True)                                         # D: stale idle clock after a see lease
c, o = run(m.cmd_ensure); age(500)
c, o = run(m.cmd_lease, ['see', '--minutes', '5', '--holder', 't']); tok = o['token']
c, o = run(m.cmd_release, [tok]); c, o = run(m.cmd_ensure)
check('D a fresh model after a lease is not parked at once', up[MIND] and o['did'] == [])

reset()                                                # E: text starts during an agent lease
c, o = run(m.cmd_lease, ['agent', '--minutes', '5', '--holder', 't']); up[MIND] = True
c, o = run(m.cmd_ensure); check('E a model started during an agent lease is stopped, lease kept', not up[MIND] and m.lease_now() is not None)

reset()                                                # F: status and list
check('F list names the agent job', 'agent' in json.loads(json.dumps(m.JOBS)))

reset()                                                # G: ensure ends a lease whose clock has run out
c, o = run(m.cmd_lease, ['agent', '--minutes', '5', '--holder', 't'])
l = m.read(m.LEASE); l['ends'] = time.monotonic() - 10; m.write(m.LEASE, l)
c, o = run(m.cmd_ensure)
check('G ensure ends a lease that ran out and brings text and search back',
      up[MIND] and up[SEARCH] and m.read(m.LEASE) is None and 'ran out' in o['did'][0])

reset()                                                # H: a second lease on a lent Kirpi is refused
c, o = run(m.cmd_lease, ['agent', '--minutes', '5', '--holder', 't']); before = m.read(m.LEASE)
c, o = run(m.cmd_lease, ['agent', '--minutes', '5', '--holder', 'other'])
check('H a lease on a job that already has one is refused with exit 2, lease unchanged',
      c == 2 and o['error'] == 'Kirpi is already lent' and o['holder'] == 't'
      and m.read(m.LEASE) == before and before['holder'] == 't' and not up[MIND])

reset()                                                # I: release with a wrong token
c, o = run(m.cmd_lease, ['agent', '--minutes', '5', '--holder', 't']); before = m.read(m.LEASE)
c, o = run(m.cmd_release, ['not-the-token'])
check('I release with a wrong token exits 2 and leaves the lease alone', c == 2 and o['error'] == 'no lease with that token' and m.read(m.LEASE) == before and not up[MIND])

reset()                                                # J: a stale timer for an old lease fires while a newer lease runs
c, o = run(m.cmd_lease, ['agent', '--minutes', '5', '--holder', 'old']); old = o['token']
c, o = run(m.cmd_release, [old])
c, o = run(m.cmd_lease, ['agent', '--minutes', '5', '--holder', 'new']); before = m.read(m.LEASE)
c, o = run(m.cmd_release, [old], True)
check('J a stale expiry timer exits 0 and leaves a newer lease alone', c == 0 and m.read(m.LEASE) == before and not up[MIND])
alive, stopped = {4242: True}, []                      # K to Q: a working chat holds Kirpi; the model's work waits
m.chat_alive = lambda pid: alive.get(pid, False)
m.stop_chat = lambda pid: (stopped.append(pid), alive.update({pid: False}))

reset(on=True)                                         # K: the chat lease parks the large model and keeps search
c, o = run(m.cmd_lease, ['chat', '--minutes', '120', '--holder', 'aiden-work0001']); tok = o['token']
check('K a chat lease parks the large model and keeps search up', c == 0 and not up[MIND] and up[SEARCH])
c, o = run(m.cmd_hold, [tok, '4242']); check('K hold names the chat process', c == 0 and m.read(m.LEASE)['pid'] == 4242)
c, o = run(m.cmd_ensure); check('K ensure leaves a living chat and its parked model alone', not up[MIND] and up[SEARCH] and m.read(m.LEASE))
up[SEARCH] = False; c, o = run(m.cmd_ensure); check('K ensure brings search back under a chat lease', up[SEARCH] and not up[MIND])

c, o = run(m.cmd_wake, ['--holder', 'filer'])          # L: a wake during the chat is queued, not lost
check('L a wake during a chat is answered queued and noted', c == 2 and o.get('queued') and m.read(m.WAITING)['count'] == 1 and not up[MIND])
c, o = run(m.cmd_wake, ['--holder', 'filer']); check('L a second wake is counted', m.read(m.WAITING)['count'] == 2)
check('L status shows who waits', m.status()['waiting'] == 2)

alive[4242] = False; c, o = run(m.cmd_ensure)          # M: the chat ends, the model is owed a turn
check('M when the chat ends the model loads by itself, because it was asked for', up[MIND] and m.read(m.LEASE) is None and m.read(m.WAITING) is None)

reset(on=True); alive[4242] = True                     # N: the chat ends and nobody asked: stay parked
c, o = run(m.cmd_lease, ['chat', '--minutes', '120', '--holder', 'aiden-work0001']); run(m.cmd_hold, [o['token'], '4242'])
c, o = run(m.cmd_chat_end, ['aiden-work0001'])
check('N chat-end with nobody waiting leaves the model parked', c == 0 and not up[MIND] and m.read(m.LEASE) is None and os.path.exists(m.PARKED))
c, o = run(m.cmd_chat_end, ['aiden-work0001']); check('N chat-end twice is harmless', c == 0)

reset(on=True)                                         # O: time is up, nobody waits: the chat keeps Kirpi
c, o = run(m.cmd_lease, ['chat', '--minutes', '120', '--holder', 'aiden-work0001']); run(m.cmd_hold, [o['token'], '4242'])
l = m.read(m.LEASE); l['ends'] = time.monotonic() - 5; m.write(m.LEASE, l); stopped.clear()
c, o = run(m.cmd_ensure)
check('O a chat past its time keeps Kirpi while nobody asks for the model', m.lease_now() is not None and not stopped and not up[MIND])

run(m.cmd_wake, ['--holder', 'filer'])                 # P: time is up and the model was asked for: the chat stops
l = m.read(m.LEASE); l['ends'] = time.monotonic() - 5; m.write(m.LEASE, l)
c, o = run(m.cmd_ensure)
check('P a chat past its time is stopped when the model was asked for, and the model loads', stopped == [4242] and up[MIND] and m.read(m.LEASE) is None)

reset(on=True); alive[4242] = True                     # Q: a chat never cuts an answer
m.busy = lambda: True
c, o = run(m.cmd_lease, ['chat', '--minutes', '120', '--holder', 'aiden-work0001'])
check('Q a chat lease is refused while the model is answering', c == 2 and up[MIND] and m.read(m.LEASE) is None)
m.busy = lambda: False
print('\n%s' % ('ALL PASS' if not fails else 'FAILED: ' + '; '.join(fails)))
sys.exit(1 if fails else 0)
