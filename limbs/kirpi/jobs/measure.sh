#!/bin/bash
# Measures, on Kirpi, what the five jobs cost: an embedding model beside Qwen,
# whisper beside Qwen, how long a switch takes, and Qwen with its eyes.
# Runs as the machine's ordinary user, needs no password, installs nothing outside ~/kimera.
# The text model on 127.0.0.1:8080 is down twice: a restart (seconds) and the
# eyes test (minutes). It is always started again at the end.
set -u
K=$HOME/kimera; M=$K/models; W=$K/measure; R=$W/results.txt
BIN=$K/llama.cpp/build/bin/llama-server
mkdir -p "$W"; : > "$R"
say() { echo "$*" >> "$R"; }
now() { date +%s.%N; }
since() { awk -v a="$1" -v b="$(now)" 'BEGIN{printf "%.1f", b-a}'; }
avail() { awk '/MemAvailable/{printf "%d", $2/1024}' /proc/meminfo; }
rss() { awk '/VmRSS/{r=$2} /RssAnon/{a=$2} /VmHWM/{h=$2} END{printf "rss=%dMB anon=%dMB peak=%dMB", r/1024, a/1024, h/1024}' "/proc/$1/status" 2>/dev/null; }
health() { curl -s -o /dev/null -m 3 -w '%{http_code}' "http://127.0.0.1:$1/health"; }
wait_up() { for _ in $(seq 1 240); do [ "$(health "$1")" = 200 ] && return 0; sleep 0.5; done; return 1; }
low_start() { ( m=999999; while :; do a=$(avail); [ "$a" -lt "$m" ] && m=$a && echo "$m" > "$W/low"; sleep 1; done ) & LOW=$!; }
low_stop() { kill "$LOW" 2>/dev/null; wait "$LOW" 2>/dev/null; cat "$W/low"; }
PIDS=""
finish() { for p in $PIDS; do kill "$p" 2>/dev/null; done; systemctl --user start kimera-mind; wait_up 8080 && say "end: text model back on 8080" || say "end: TEXT MODEL DID NOT COME BACK"; say "DONE $(date +%H:%M)"; }
trap finish EXIT
get() { # url file
  [ -s "$2" ] && { say "have $(basename "$2")"; return; }
  t=$(now); curl -sL -C - --retry 5 -o "$2.part" "$1" && mv "$2.part" "$2"
  say "download $(basename "$2") $(du -m "$2" | cut -f1)MB in $(since "$t")s sha256=$(sha256sum "$2" | cut -c1-64)"
}
chat() { # port json -> prints content, usage, seconds
  t=$(now); curl -s -m 900 "http://127.0.0.1:$1/v1/chat/completions" -H 'content-type: application/json' -d @"$2" > "$W/reply.json"
  python3 - "$W/reply.json" "$(since "$t")" <<'P'
import json,sys
try:
    d=json.load(open(sys.argv[1])); u=d.get('usage',{}); tm=d.get('timings',{})
    print(f"seconds={sys.argv[2]} in={u.get('prompt_tokens')} out={u.get('completion_tokens')} read_tps={tm.get('prompt_per_second',0):.1f} write_tps={tm.get('predicted_per_second',0):.1f} text={d['choices'][0]['message']['content'][:400]!r}")
except Exception as e:
    print(f"seconds={sys.argv[2]} FAILED {e} {open(sys.argv[1]).read()[:300]!r}")
P
}
cat > "$W/text.json" <<'J'
{"model":"qwen3.5-4b","messages":[{"role":"user","content":"Name three animals that live in a forest, one line each."}],"max_tokens":40,"temperature":0,"chat_template_kwargs":{"enable_thinking":false}}
J

say "START $(date '+%F %H:%M') available=$(avail)MB mind=$(systemctl --user is-active kimera-mind)"
MIND=$(systemctl --user show -p MainPID --value kimera-mind); say "qwen at rest: $(rss "$MIND")"

# A. downloads, from the makers' own repositories
get https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/main/mmproj-F16.gguf "$M/qwen3.5-4b-mmproj-F16.gguf"
get https://huggingface.co/Qwen/Qwen3-Embedding-0.6B-GGUF/resolve/main/Qwen3-Embedding-0.6B-Q8_0.gguf "$M/Qwen3-Embedding-0.6B-Q8_0.gguf"
get https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin "$M/ggml-base.bin"
get https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small-q5_1.bin "$M/ggml-small-q5_1.bin"

# B. whisper.cpp from source, newest release tag
if [ ! -x "$K/whisper.cpp/build/bin/whisper-cli" ]; then
  tag=$(git ls-remote --tags --refs https://github.com/ggml-org/whisper.cpp 'v*' | awk -F/ '{print $3}' | sort -V | tail -1)
  t=$(now); rm -rf "$K/whisper.cpp"
  git clone -q --depth 1 --branch "$tag" https://github.com/ggml-org/whisper.cpp "$K/whisper.cpp" \
   && cmake -S "$K/whisper.cpp" -B "$K/whisper.cpp/build" -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=ON -DWHISPER_BUILD_TESTS=OFF > "$W/whisper-build.log" 2>&1 \
   && cmake --build "$K/whisper.cpp/build" -j2 --target whisper-cli >> "$W/whisper-build.log" 2>&1
  say "whisper.cpp $tag built in $(since "$t")s: $([ -x "$K/whisper.cpp/build/bin/whisper-cli" ] && echo ok || echo FAILED)"
fi

# C. the embedding model beside Qwen
low_start; t=$(now)
"$BIN" -m "$M/Qwen3-Embedding-0.6B-Q8_0.gguf" --alias embed --embedding --pooling last --host 127.0.0.1 --port 8081 -c 2048 -np 1 -t 4 --no-webui > "$W/embed.log" 2>&1 &
E=$!; PIDS="$PIDS $E"
if wait_up 8081; then
  say "embed: ready in $(since "$t")s, $(rss "$E"), available=$(avail)MB"
  python3 - > "$W/embed.out" 2>&1 <<'P'
import json,time,urllib.request
def emb(texts):
    r=urllib.request.Request('http://127.0.0.1:8081/v1/embeddings',json.dumps({'model':'embed','input':texts}).encode(),{'content-type':'application/json'})
    t=time.time(); d=json.load(urllib.request.urlopen(r,timeout=600)); return time.time()-t,d
para=("Kirpi is a small laptop that holds one model in memory and answers on its own address. "
      "Bugün Kirpi'nin ekranında kirpi, işler ve saat var; model bekliyor. ")
s,d=emb(["warm up"])
s,d=emb([para*12]); n=d['usage']['prompt_tokens']; print(f"embed: one long text {n} tokens in {s:.1f}s = {n/s:.0f} tokens/s, {len(d['data'][0]['embedding'])} numbers")
short=[f"Note {i}: the model on Kirpi wrote a riddle about a candle." for i in range(10)]
s,d=emb(short); n=d['usage']['prompt_tokens']; print(f"embed: ten short texts {n} tokens in {s:.1f}s")
import math
def cos(a,b): return sum(x*y for x,y in zip(a,b))/math.sqrt(sum(x*x for x in a)*sum(y*y for y in b))
s,d=emb(["The cat sleeps on the sofa.","Kedi kanepede uyuyor.","The invoice is due on Friday."]); v=[x['embedding'] for x in d['data']]
print(f"embed: English/Turkish same meaning {cos(v[0],v[1]):.2f}, unrelated {cos(v[0],v[2]):.2f}")
P
  cat "$W/embed.out" >> "$R"
  say "qwen while the embedder is loaded: $(chat 8080 "$W/text.json")"
  say "embed: after use $(rss "$E"), available=$(avail)MB"
else say "embed: DID NOT START: $(tail -3 "$W/embed.log" | tr '\n' ' ')"; fi
say "embed: lowest available during the test $(low_stop)MB"

# D. whisper beside Qwen and the embedder (the worst case), then beside Qwen alone
WC=$K/whisper.cpp/build/bin/whisper-cli; WAV=$K/whisper.cpp/samples/jfk.wav
hear() { # label model
  low_start; t=$(now); "$WC" -m "$2" -f "$WAV" -t 4 -l auto > "$W/whisper.out" 2>&1
  say "hear $1: $(since "$t")s for an 11 s clip; $(grep -E 'load time|encode time|decode time|total time' "$W/whisper.out" | sed -E 's/.*: +//;s/ +/ /g' | tr '\n' ';'); lowest available $(low_stop)MB; text=$(grep -E '^\[' "$W/whisper.out" | head -2 | cut -c1-140 | tr '\n' ' ')"
}
if [ -x "$WC" ]; then
  hear "base, with qwen+embedder" "$M/ggml-base.bin"
  hear "small-q5, with qwen+embedder" "$M/ggml-small-q5_1.bin"
  kill "$E" 2>/dev/null; wait "$E" 2>/dev/null; sleep 2
  hear "base, with qwen" "$M/ggml-base.bin"
  hear "small-q5, with qwen" "$M/ggml-small-q5_1.bin"
fi
kill "$E" 2>/dev/null; wait "$E" 2>/dev/null

# E. how long a switch takes: stop the text model and start it again
t=$(now); systemctl --user restart kimera-mind; wait_up 8080
say "switch: text model stop and start, ready in $(since "$t")s"
say "switch: first answer after it $(chat 8080 "$W/text.json")"

# F. Qwen with its eyes (the text model is off during this)
systemctl --user stop kimera-mind; sleep 2; say "eyes: text model stopped, available=$(avail)MB"
low_start; t=$(now)
"$BIN" -m "$M/Qwen3.5-4B-Q4_K_S.gguf" --mmproj "$M/qwen3.5-4b-mmproj-F16.gguf" --alias qwen3.5-4b --host 127.0.0.1 --port 8090 -c 4096 -np 1 -t 4 --no-webui --cache-ram 0 > "$W/eyes.log" 2>&1 &
V=$!; PIDS="$PIDS $V"
if wait_up 8090; then
  say "eyes: ready in $(since "$t")s, $(rss "$V"), available=$(avail)MB"
  say "eyes: plain text $(chat 8090 "$W/text.json")"
  for q in "Write out every word you can read in this picture, nothing else." "Describe this picture in two sentences."; do
    python3 - "$W/shot.png" "$q" > "$W/see.json" <<'P'
import base64,json,sys
b=base64.b64encode(open(sys.argv[1],'rb').read()).decode()
print(json.dumps({"model":"qwen3.5-4b","messages":[{"role":"user","content":[{"type":"text","text":sys.argv[2]},{"type":"image_url","image_url":{"url":"data:image/png;base64,"+b}}]}],"max_tokens":150,"temperature":0,"chat_template_kwargs":{"enable_thinking":False}}))
P
    say "eyes: \"$q\" $(chat 8090 "$W/see.json")"
  done
  say "eyes: after use $(rss "$V"), available=$(avail)MB"
else say "eyes: DID NOT START: $(tail -4 "$W/eyes.log" | tr '\n' ' ')"; fi
say "eyes: lowest available during the test $(low_stop)MB, swap used $(awk '/SwapTotal/{t=$2}/SwapFree/{f=$2}END{printf "%d",(t-f)/1024}' /proc/meminfo)MB"
kill "$V" 2>/dev/null; wait "$V" 2>/dev/null
