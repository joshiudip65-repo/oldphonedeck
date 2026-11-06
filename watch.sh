#!/bin/bash
# OldPhoneDeck watcher — brings the deck up automatically over USB *or* Wi-Fi.
# Prefers the cable; falls back to Wi-Fi (adb tcpip). Self-heals DHCP changes by
# re-scanning the LAN for the phone when its cached IP stops responding.
set -u
export PATH="/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:/Library/Frameworks/Python.framework/Versions/3.13/bin:$PATH"

DIR="$HOME/oldphonedeck"
CFG="$DIR/config.json"
CACHE="$DIR/.phone_ip"
SERIAL=$(python3 -c "import json;print(json.load(open('$CFG')).get('target_serial',''))")
WPORT=$(python3 -c "import json;print(json.load(open('$CFG')).get('wireless_port',5555))")

# current best-known wifi endpoint: cache file wins, else config
if [ -f "$CACHE" ]; then
  WDEV="$(cat "$CACHE"):$WPORT"
else
  WIP=$(python3 -c "import json;print(json.load(open('$CFG')).get('phone_ip',''))")
  WDEV="${WIP:+$WIP:$WPORT}"
fi

prevdev=""
rediscover_in=0
while true; do
  dev=""
  if [ -n "$SERIAL" ] && [ "$(adb -s "$SERIAL" get-state 2>/dev/null)" = "device" ]; then
    dev="$SERIAL"                                   # USB cable wins
  else
    # try the known wifi endpoint
    if [ -n "$WDEV" ]; then
      adb connect "$WDEV" >/dev/null 2>&1
      [ "$(adb -s "$WDEV" get-state 2>/dev/null)" = "device" ] && dev="$WDEV"
    fi
    # not reachable? rediscover on the LAN (throttled, ~every 21s)
    if [ -z "$dev" ]; then
      if [ "$rediscover_in" -le 0 ]; then
        found=$(python3 "$DIR/find_phone.py" 2>/dev/null)
        if [ -n "$found" ]; then
          WDEV="$found"
          echo "${found%:*}" > "$CACHE"
          echo "$(date '+%F %H:%M:%S') rediscovered phone at $found"
          dev="$WDEV"
        fi
        rediscover_in=7
      else
        rediscover_in=$((rediscover_in - 1))
      fi
    fi
  fi

  if [ -n "$dev" ] && [ "$dev" != "$prevdev" ]; then
    echo "$(date '+%F %H:%M:%S') active device: $dev → launching deck"
    bash "$DIR/connect.sh" "$dev"
  elif [ -z "$dev" ] && [ -n "$prevdev" ]; then
    echo "$(date '+%F %H:%M:%S') phone not reachable (no USB, no Wi-Fi)"
  fi
  prevdev="$dev"
  sleep 3
done
