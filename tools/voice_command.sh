#!/usr/bin/env bash
# Voice -> game command test (works with Wi-Fi off). Needs 3 servers running: Argmax :50060, Bonsai :1234, backend :8000.
#   bash ~/argmax/voice_command.sh                 # loop: press Enter, speak for 4 s, see + hear the result
#   AUDIO=file.wav bash ~/argmax/voice_command.sh  # use a recorded file instead of the mic (one round)
#   SAY=0 ...                                      # don't speak the reply
#   PLAYER_X=18 ...                                # pretend the player is at tile x=18 (for "make this harder", "in front of me")
set -u
MIC="MacBook Air Microphone"
SECS=${SECS:-4}
A=~/argmax/argmax-oss-swift
TMP=/tmp/voice_cmd.wav
B=http://localhost:8000

for s in "Argmax:http://localhost:50060/health" "Bonsai:http://localhost:1234/v1/models" "Backend:$B/api/health"; do
  curl -s -m 3 -o /dev/null "${s#*:}" || { echo "${s%%:*} server is not running (${s#*:}). See ~/argmax/VOICE_TEST.md"; exit 1; }
done

round() {
  local f=$1
  echo "... transcribing (Argmax)"
  local tr; tr=$(curl -s -m 120 $B/api/transcribe -F "audio=@$f")
  local text; text=$(python3 -c 'import sys,json; d=json.loads(sys.argv[1]); print(d.get("text",""))' "$tr" 2>/dev/null)
  local tms; tms=$(python3 -c 'import sys,json; print(json.loads(sys.argv[1]).get("latency_ms","?"))' "$tr" 2>/dev/null)
  if [ -z "$text" ]; then echo "    heard nothing ($tr)"; return; fi
  echo "    heard: \"$text\"  (${tms} ms)"
  echo "... thinking (Bonsai 4B)"
  local player=null
  [ -n "${PLAYER_X:-}" ] && player="{\"x\":$PLAYER_X,\"y\":12,\"has_double_jump\":false}"
  local body; body=$(python3 -c 'import sys,json; print(json.dumps({"text":sys.argv[1],"source":"voice","speaker":None,"player":json.loads(sys.argv[2])}))' "$text" "$player")
  local res; res=$(curl -s -m 180 $B/api/command -H 'Content-Type: application/json' -d "$body")
  python3 - "$res" <<'EOF'
import sys, json
d = json.loads(sys.argv[1])
print(f"    status: {d['status']}   model: {d['model']}   latency: {d['latency_ms']} ms   version: {d['version']}")
print(f"    copilot says: \"{d['spoken']}\"")
if d.get("reason"): print(f"    reason: {d['reason']}")
for op in d["patch"]:
    if op["op"] == "add_entity":
        e = op["entity"]; print(f"      + add {e['type']} {e['id']} at x={e['x']}, y={e['y']}")
    elif op["op"] == "update_entity": print(f"      ~ {op['id']}: {op['changes']}")
    elif op["op"] == "remove_entity": print(f"      - remove {op['id']}")
    else: print(f"      * {op}")
open("/tmp/voice_spoken.txt", "w").write(d["spoken"])
EOF
  if [ "${SAY:-1}" = "1" ] && [ -s /tmp/voice_spoken.txt ]; then
    echo "... speaking (Argmax TTS)"
    (cd $A && .build/release/argmax-cli tts --model 0.6b --models-path ~/Documents/huggingface/models/argmaxinc/ttskit-coreml \
       --text "$(cat /tmp/voice_spoken.txt)" --play >/dev/null 2>&1)
  fi
  echo "    -> refresh the game tab (http://localhost:8000) to see the change. Undo: curl -s -X POST $B/api/undo >/dev/null"
}

if [ -n "${AUDIO:-}" ]; then round "$AUDIO"; exit; fi
echo "Voice commands. Try: \"lower the gravity\", \"add three enemies near the end\", \"make the gaps bigger\", \"give me fireballs\". Ctrl-C to quit."
while true; do
  echo ""; read -r -p ">>> Press Enter, then speak (${SECS} s)... " _
  ffmpeg -hide_banner -loglevel error -y -f avfoundation -i ":$MIC" -t "$SECS" -ac 1 -ar 16000 $TMP || { echo "mic recording failed (allow microphone access for Terminal in System Settings > Privacy)"; continue; }
  round $TMP
done
