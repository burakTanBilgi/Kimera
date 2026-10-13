#!/usr/bin/env bash
# install-device.sh DEVICE   (run on Tilki; no sudo anywhere)
# Puts the seat road on one device: the kimera-seat forced command, the seat config and toolset files, the seat
# folders, and the three key pairs on Tilki. It does NOT touch the device's authorized_keys: that is
# authorize-device.sh, run only on Tan's word. Safe to run again.
set -euo pipefail
DEV="${1:?device name from devices.json}"
HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
CONF="${KIMERA_DEVICES:-$HOME/.config/kimera/devices.json}"
eval "$(python3 - "$CONF" "$DEV" <<'P'
import json, shlex, sys
r = json.load(open(sys.argv[1]))[sys.argv[2]]
print('SSH=(%s)' % ' '.join(shlex.quote(x) for x in r['ssh']))
print('CFG=%s' % shlex.quote(r['config_dir']))
print('ROOTS=%s' % shlex.quote(' '.join(r['seat_roots'])))
print('CLAUDE=%s' % shlex.quote(r['claude']))
print('PORT=%d' % r['hook_port'])
print('TOKEN=%s' % shlex.quote(r['hook_token_file']))
print('CHAT=%s' % ('1' if r.get('chat') else '0'))
print('SEATJSON=%s' % shlex.quote(json.dumps({k: r.get(k) for k in ('chat', 'why_not', 'seat_roots', 'config_dir', 'claude', 'limits', 'modes', 'box_mb', 'tmux', 'tools_force')} | {'hook_port': r['hook_port'], 'hook_token_file': r['hook_token_file']})))
P
)"
HOME_D="$("${SSH[@]}" 'printf %s "$HOME"')"
for k in seat mirror hooks; do
  f="$HOME/.ssh/kimera-$k-$DEV"
  [[ -f "$f" ]] || ssh-keygen -q -t ed25519 -N '' -C "kimera-$k-$DEV" -f "$f"
done
"${SSH[@]}" "mkdir -p ~/kimera/bin ~/.config/kimera/seat ~/.local/state/kimera && chmod 700 ~/.config/kimera"
"${SSH[@]}" "cat > ~/kimera/bin/kimera-seat" < "$HERE/../../seat/kimera-seat"
"${SSH[@]}" "chmod 755 ~/kimera/bin/kimera-seat"
"${SSH[@]}" "cat > ~/.config/kimera/seat/seat.json" <<<"$SEATJSON"
"${SSH[@]}" "printf '%s\n' '{\"mcpServers\":{}}' > ~/.config/kimera/seat/mcp-empty.json"
# settings.json (hooks, plugins off) is AIDEN's content; keep what is there, create a plugins-off base once.
"${SSH[@]}" "python3 -c '
import json, os, sys
seat = os.path.expanduser(\"~/.config/kimera/seat\")
pr, cur = os.path.join(seat, \"settings.pristine.json\"), os.path.join(seat, \"settings.json\")
base = {\"enabledPlugins\": {}}
if os.path.exists(pr):
    sys.exit(0)
try:
    have = json.load(open(cur))
except (OSError, ValueError):
    have = None
if have is None or have == base:  # nothing there, or exactly the known baseline: safe to start from it
    open(pr, \"w\").write(json.dumps(base, indent=1))
    open(cur, \"w\").write(json.dumps(base, indent=1))
else:  # an unknown settings.json is never adopted as the baseline, and never overwritten
    pass  # no pristine yet: the check at the end decides; AIDEN_HOOK_SCRIPT (below) replaces the file and writes it
'"
# The hooks block and AIDEN's hook script (v0.40.0) are placed only when AIDEN_HOOK_SCRIPT names the shipped script;
# a block that points at a missing script would make every chat's hooks fail. The block is a template: __SEAT_DIR__
# becomes this device user's own seat folder. The file is REPLACED whole, never merged: a settings.json a chat has
# edited (permissions, env, other hooks) must not survive. The previous one is kept as settings.json.prev to look at.
if [[ -n "${AIDEN_HOOK_SCRIPT:-}" ]]; then
  "${SSH[@]}" "umask 077; cat > ~/.config/kimera/seat/aiden-hook.sh.new && chmod 755 ~/.config/kimera/seat/aiden-hook.sh.new && mv ~/.config/kimera/seat/aiden-hook.sh.new ~/.config/kimera/seat/aiden-hook.sh" < "$AIDEN_HOOK_SCRIPT"
  "${SSH[@]}" "python3 -c '
import json, os, sys
seat = os.path.expanduser(\"~/.config/kimera/seat\")
new = json.loads(sys.stdin.read().replace(\"__SEAT_DIR__\", seat))
p = os.path.join(seat, \"settings.json\")
try:
    cur = json.load(open(p))
except (OSError, ValueError):
    cur = {}
if cur and cur != new:  # copy, never move: settings.json must exist at every instant
    open(p + \".prev\", \"w\").write(json.dumps(cur, indent=1))
open(p + \".new\", \"w\").write(json.dumps(new, indent=1))
os.replace(p + \".new\", p)
open(os.path.join(seat, \"settings.pristine.json\"), \"w\").write(json.dumps(new, indent=1))
'" < "$HERE/../../seat/settings.hooks.json"
fi
# AIDEN_HOOK_TOKEN: path to the minted token file on Tilki; the value never goes through argv. An existing token is
# kept unless AIDEN_HOOK_TOKEN_ROTATE=1.
if [[ -n "${AIDEN_HOOK_TOKEN:-}" ]]; then
  "${SSH[@]}" "umask 077; t=~/.config/kimera/hook-token; if [ -e \$t ] && [ '${AIDEN_HOOK_TOKEN_ROTATE:-0}' != 1 ]; then cat >/dev/null; echo token-kept; else cat > \$t.new && mv \$t.new \$t; echo token-placed; fi" < "$AIDEN_HOOK_TOKEN"
fi
# Fail closed, last: with no pristine copy a seat will not start. Reached only when nothing above could make one.
"${SSH[@]}" "test -f ~/.config/kimera/seat/settings.pristine.json" || {
  echo "settings.json differs from the known baseline and no AIDEN_HOOK_SCRIPT was given: inspect ~/.config/kimera/seat/settings.json, then delete it or rerun with AIDEN_HOOK_SCRIPT" >&2
  exit 3
}
for r in $ROOTS; do "${SSH[@]}" "mkdir -p '$r' && chmod 700 '$r'"; done
# Trust the seat roots once, so a chat in a new folder under them does not stop at the folder-trust question.
"${SSH[@]}" "python3 - '$CFG' $ROOTS" <<'P'
import json, os, sys
p = os.path.join(sys.argv[1], '.claude.json')
d = json.load(open(p)) if os.path.exists(p) else {}
for root in sys.argv[2:]:
    d.setdefault('projects', {}).setdefault(root, {})['hasTrustDialogAccepted'] = True
json.dump(d, open(p + '.kimera', 'w'), indent=2)
os.chmod(p + '.kimera', 0o600)
os.replace(p + '.kimera', p)
P
python3 - "$CONF" "$DEV" "$HOME/.ssh/kimera-seat-$DEV" <<'P'
import json, sys
c = json.load(open(sys.argv[1]))
c[sys.argv[2]].setdefault('run', {}).update(key=sys.argv[3].replace(__import__('os').path.expanduser('~'), '~'))
json.dump(c, open(sys.argv[1], 'w'), indent=2)
P
echo "installed on $DEV: seat files and keys on Tilki; hook script $([ -n "${AIDEN_HOOK_SCRIPT:-}" ] && echo placed || echo "not placed"), token $([ -n "${AIDEN_HOOK_TOKEN:-}" ] && echo placed || echo "not placed")"
