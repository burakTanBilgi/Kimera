#!/bin/bash
# Tests the switch on the real Kirpi, from Tilki. Prints one line per check (29 lines: checks 1 to 26, three of them in parts).
# It borrows the machine for several minutes: it switches the large model, stops it by hand and lets leases run out.
#   KIRPI_SSH="ssh -o BatchMode=yes USER@HOST" ./test-switch.sh
K="${KIRPI_SSH:?set KIRPI_SSH to the ssh command for the machine, for example: ssh -o BatchMode=yes USER@HOST}"; J="kimera/bin/kimera-job"
ok() { echo "PASS $1"; }; no() { echo "FAIL $1 :: $2"; }
has() { case "$2" in *"$3"*) ok "$1";; *) no "$1" "$2";; esac; }
field() { python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(eval(sys.argv[2]))" "$1" "$2" 2>/dev/null; }
ask() { $K "curl -s -m 300 http://127.0.0.1:8080/v1/chat/completions -H 'content-type: application/json' -d @-" ; }
T='{"model":"qwen3.5-4b","messages":[{"role":"user","content":"Say only: yes"}],"max_tokens":8,"temperature":0,"chat_template_kwargs":{"enable_thinking":false}}'
LONG='{"model":"qwen3.5-4b","messages":[{"role":"user","content":"Write a story about a hedgehog who repairs clocks."}],"max_tokens":170,"temperature":0,"chat_template_kwargs":{"enable_thinking":false}}'

r=$($K $J lease dance --minutes 5); has "1 unknown job is refused" "$r" '"ok": false'
r=$($K $J frobnicate); has "2 unknown command is refused" "$r" 'unknown command'
r=$($K $J lease hear --minutes 5); has "3 hear needs no lease" "$r" 'no lease is needed'
r=$($K $J lease see); has "4 see without minutes is refused" "$r" 'minutes N is needed'
r=$($K $J status); has "5 at rest: text, ready" "$r" '"job": "text", "state": "ready"'

t=$(date +%s); r=$($K $J lease see --minutes 3 --holder test); tok=$(field "$r" "d['token']")
[ -n "$tok" ] && ok "6 lease see granted in $(( $(date +%s)-t )) s" || no "6 lease see" "$r"
r=$($K $J status); has "7 status: see, ready, lent to test" "$r" '"job": "see", "state": "ready"'; has "7b search is off meanwhile" "$r" 'off while the model has its eyes'
r=$(echo "$T" | ask); has "8 text still answers under the same name" "$r" '"model":"qwen3.5-4b"'
r=$($K "python3 - <<'P'
import base64,json,urllib.request,time
b=base64.b64encode(open(__import__('os').path.expanduser('~/kimera/measure/shot.png'),'rb').read()).decode()
q={'model':'qwen3.5-4b','messages':[{'role':'user','content':[{'type':'text','text':'What is the title written at the top of this picture? Only the title.'},{'type':'image_url','image_url':{'url':'data:image/png;base64,'+b}}]}],'max_tokens':20,'temperature':0,'chat_template_kwargs':{'enable_thinking':False}}
t=time.time(); d=json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8080/v1/chat/completions',json.dumps(q).encode(),{'content-type':'application/json'}),timeout=300))
print(d['choices'][0]['message']['content'].strip(), '| %.0f s' % (time.time()-t))
P"); has "9 it reads a picture ($r)" "$r" 'Riddle Moth'
r=$($K $J lease see --minutes 3 --holder other); has "10 a second lease is refused, names the holder" "$r" '"holder": "test"'
r=$($K $J release 0000); has "11 a wrong token is refused" "$r" 'no lease with that token'
t=$(date +%s); r=$($K $J release "$tok"); has "12 release returns to text in $(( $(date +%s)-t )) s" "$r" '"ok": true'
r=$($K $J status); has "13 after release: text, ready, search back, no lease" "$r" '"job": "text", "state": "ready"'; has "13b" "$r" '"search": "ready"'; has "13c" "$r" '"lease": null'

r=$($K $J lease see --minutes 1 --holder forgetful); tok=$(field "$r" "d['token']"); t=$(date +%s)
( sleep 8; $K $J status > /tmp/kimera-mid.txt ) & 
for i in $(seq 1 30); do sleep 5; r=$($K $J status); case "$r" in *'"job": "text", "state": "ready"'*'"lease": null'*) break;; esac; done
has "14 a forgotten lease ends by itself, back on text after $(( $(date +%s)-t )) s" "$r" '"job": "text", "state": "ready"'

echo "$LONG" | ask > /tmp/kimera-long.json & A=$!
sleep 4; r=$($K $J status); has "15 status says busy during an answer" "$r" '"busy": true'
t=$(date +%s); r=$($K $J lease see --minutes 2 --holder patient); tok=$(field "$r" "d['token']"); w=$(( $(date +%s)-t ))
wait $A; n=$(field "$(cat /tmp/kimera-long.json)" "d['usage']['completion_tokens']")
[ "$n" = 170 ] && ok "16 the switch waited for the answer: all $n tokens arrived, lease took $w s" || no "16 the answer was cut" "tokens=$n lease took $w s"
r=$($K $J release "$tok"); has "17 released" "$r" '"ok": true'

$K "systemctl --user stop kimera-mind"; t=$(date +%s)
for i in $(seq 1 30); do sleep 5; r=$($K $J status); case "$r" in *'"job": "text", "state": "ready"'*) break;; esac; done
has "18 text model stopped by hand comes back by itself after $(( $(date +%s)-t )) s" "$r" '"job": "text", "state": "ready"'
r=$($K "kimera/bin/kimera-hear kimera/whisper.cpp/samples/jfk.wav en"); has "19 hear turns speech into text" "$r" 'ask not what your country can do for you'
$K "ffmpeg -nostdin -loglevel error -y -i kimera/whisper.cpp/samples/jfk.wav -c:a aac kimera/measure/jfk.m4a"
r=$($K "kimera/bin/kimera-hear kimera/measure/jfk.m4a en" 2>/dev/null); has "20 hear reads a file that needs ffmpeg" "$r" 'ask not what your country can do for you'
r=$($K "kimera/bin/kimera-ocr kimera/measure/shot.png"); has "21 the reader finds the words on a picture" "$r" 'Riddle Moth'
$K "kimera/bin/kimera-hear kimera/whisper.cpp/samples/jfk.wav en" > /tmp/kimera-hear.txt 2>/dev/null & A=$!
sleep 2; t=$(date +%s); r=$($K $J lease see --minutes 2 --holder polite); tok=$(field "$r" "d['token']"); wait $A
has "22 a lease waits for hearing to finish (lease took $(( $(date +%s)-t )) s)" "$(cat /tmp/kimera-hear.txt)" 'ask not what your country can do for you'
r=$($K "kimera/bin/kimera-hear kimera/whisper.cpp/samples/jfk.wav en" 2>&1); has "23 hear is refused while the model has its eyes" "$r" 'not while the model has its eyes'
r=$($K $J release "$tok"); has "24 released" "$r" '"ok": true'
$K 'echo "{\"from\":\"text\",\"to\":\"see\",\"since\":$(date +%s)}" > $XDG_RUNTIME_DIR/kimera/switching.json'
r=$($K $J status); has "25 a stale mark shows as switching at first" "$r" '"state": "switching"'
for i in $(seq 1 16); do sleep 5; r=$($K $J status); case "$r" in *'"job": "text", "state": "ready"'*) break;; esac; done
has "26 and is cleared by itself within $(( i*5 )) s" "$r" '"job": "text", "state": "ready"'
r=$($K "free -m | awk '/Mem/{print \$7}'; tail -12 kimera/jobs.log"); echo "--- available MB and the switch's own log"; echo "$r"
