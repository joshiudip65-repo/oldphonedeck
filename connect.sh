#!/bin/bash
# OldPhoneDeck — bring the deck up on a given device (USB serial or wifi ip:port).
#   $1 = adb device id (defaults to the USB serial from config)
# Steps: ensure helper running → (re)arm wireless if on USB → open tunnel → keep
# screen awake → launch the app.
set -u
export PATH="/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:/Library/Frameworks/Python.framework/Versions/3.13/bin:$PATH"

DIR="$HOME/oldphonedeck"
CFG="$DIR/config.json"
PORT=$(python3 -c "import json;print(json.load(open('$CFG'))['port'])")
SERIAL=$(python3 -c "import json;print(json.load(open('$CFG')).get('target_serial',''))")
PHONE_IP=$(python3 -c "import json;print(json.load(open('$CFG')).get('phone_ip',''))")
WPORT=$(python3 -c "import json;print(json.load(open('$CFG')).get('wireless_port',5555))")
APP="com.oldphonedeck/.MainActivity"
DEVICE="${1:-$SERIAL}"

# record transport (usb / wifi) for the app's status indicator
if [ "$DEVICE" = "$SERIAL" ]; then echo "usb" > "$DIR/.transport"; else echo "wifi" > "$DIR/.transport"; fi

log(){ echo "$(date '+%H:%M:%S') $*"; }

# 1. helper (binds 127.0.0.1 only; reached through the adb reverse tunnel)
if ! lsof -i :"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  log "starting helper on :$PORT"
  nohup python3 "$DIR/server.py" > "$DIR/server.log" 2>&1 &
  sleep 2
fi

# 2. if we're on USB, (re)arm wireless debugging so wifi keeps working later
#    (survives until the phone reboots; re-armed on every USB connect)
if [ "$DEVICE" = "$SERIAL" ] && [ -n "$PHONE_IP" ]; then
  adb -s "$SERIAL" tcpip "$WPORT" >/dev/null 2>&1
  sleep 2
  adb connect "$PHONE_IP:$WPORT" >/dev/null 2>&1
fi

ADB=(adb -s "$DEVICE")

# 3. USB-over-cable OR wifi tunnel — app always reaches the Mac at localhost:$PORT
"${ADB[@]}" reverse tcp:"$PORT" tcp:"$PORT" >/dev/null 2>&1 && log "tunnel :$PORT ready on $DEVICE"

# 4. keep screen awake while docked
"${ADB[@]}" shell svc power stayon true >/dev/null 2>&1

# 5. launch the deck
"${ADB[@]}" shell am start -n "$APP" >/dev/null 2>&1 && log "deck launched on $DEVICE"
