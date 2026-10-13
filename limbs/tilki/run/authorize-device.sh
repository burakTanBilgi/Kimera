#!/usr/bin/env bash
# authorize-device.sh DEVICE   (run on Tilki, only on Tan's word: it adds three restricted lines to the
# device user's ~/.ssh/authorized_keys). Each line has `restrict` (no shell, no pty, no forwarding unless named):
#   kimera-seat   : runs only ~/kimera/bin/kimera-seat (the nine verbs)
#   kimera-mirror : runs only `rrsync -ro <config dir>/projects` (read-only copy of transcripts)
#   kimera-hooks  : may only listen on 127.0.0.1:<hook_port> on the device (permitopen limited to the discard port: no useful local forwards); runs nothing
# KEYS=seat,hooks limits it to those (default: seat,mirror,hooks), so Tan can name which keys he approves.
# To undo: delete the lines ending in kimera-seat, kimera-mirror, kimera-hooks.
set -euo pipefail
DEV="${1:?device name from devices.json}"
CONF="${KIMERA_DEVICES:-$HOME/.config/kimera/devices.json}"
eval "$(python3 - "$CONF" "$DEV" <<'P'
import json, shlex, sys
r = json.load(open(sys.argv[1]))[sys.argv[2]]
print('SSH=(%s)' % ' '.join(shlex.quote(x) for x in r['ssh']))
print('CFG=%s' % shlex.quote(r['config_dir']))
print('PORT=%d' % r['hook_port'])
P
)"
HOME_D="$("${SSH[@]}" 'printf %s "$HOME"')"
S="$(cut -d' ' -f1,2 "$HOME/.ssh/kimera-seat-$DEV.pub")"
M="$(cut -d' ' -f1,2 "$HOME/.ssh/kimera-mirror-$DEV.pub")"
H="$(cut -d' ' -f1,2 "$HOME/.ssh/kimera-hooks-$DEV.pub")"
KEYS="${KEYS:-seat,mirror,hooks}"
"${SSH[@]}" "python3 - '$HOME_D' '$CFG' '$PORT' '$KEYS'" <<P
import os, sys
home, cfg, port, keys = sys.argv[1:5]
keys = keys.split(',')
want = [
  'restrict,command="%s/kimera/bin/kimera-seat" $S kimera-seat' % home,
  'restrict,command="/usr/bin/rrsync -ro %s/projects" $M kimera-mirror' % cfg,
  'restrict,port-forwarding,permitopen="127.0.0.1:9",permitlisten="127.0.0.1:%s",command="/bin/false" $H kimera-hooks' % port,
]
names = ['seat', 'mirror', 'hooks']
if not keys or any(k not in names for k in keys):
    sys.exit('KEYS must be some of seat,mirror,hooks')
# every one of our keys is cleaned of weaker lines, chosen or not; only the chosen ones are (re)added
blobs = [w.split()[-2] for w in want]
chosen = [w.split()[-2] for n, w in zip(names, want) if n in keys]
all_want = list(want)
want = [w for n, w in zip(names, want) if n in keys]
p = os.path.join(home, '.ssh/authorized_keys')
lines = open(p).read().splitlines() if os.path.exists(p) else []
# a line holding one of our keys under any other options (for example none) would bypass restrict: drop it, then add ours
# a chosen key's lines are all replaced. An unchosen key keeps a line only if it is EXACTLY the line we would write
# (a restrict prefix proves nothing: a line with restrict,pty,agent-forwarding would pass); any other line holding
# one of our keys is dropped.
exact = set(all_want)
kept = [l for l in lines if not any(b in l for b in blobs) or (l in exact and not any(c in l for c in chosen))]
dropped = len(lines) - len(kept)
tmp = p + '.kimera'
with open(tmp, 'w') as f:
    f.write('\n'.join(kept + want) + '\n')
os.chmod(tmp, 0o600)
os.replace(tmp, p)
add = want
print('authorized_keys: added %d line(s)' % len(add))
P
echo "authorized on $DEV"
python3 - "$CONF" "$DEV" <<'P'
import json, sys
c = json.load(open(sys.argv[1]))
c[sys.argv[2]].setdefault('run', {})['authorized'] = True
json.dump(c, open(sys.argv[1], 'w'), indent=2)
P
