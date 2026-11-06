#!/bin/bash
# OldPhoneDeck smart media control: play|next|prev.
# Prefers Spotify, then Music (reliable AppleScript, works from the background
# server), and falls back to the system media key for browser video (YouTube etc.).
# Never launches an app.
DIR="$HOME/oldphonedeck"
CMD="${1:-play}"
case "$CMD" in
  next) SP="next track";      MK="next" ;;
  prev) SP="previous track";  MK="prev" ;;
  *)    SP="playpause";       MK="play" ;;
esac

acted=$(osascript \
  -e 'set acted to "no"' \
  -e 'if application "Spotify" is running then' \
  -e "  tell application \"Spotify\" to $SP" \
  -e '  set acted to "yes"' \
  -e 'end if' \
  -e 'if acted is "no" and application "Music" is running then' \
  -e "  tell application \"Music\" to $SP" \
  -e '  set acted to "yes"' \
  -e 'end if' \
  -e 'return acted' 2>/dev/null)

[ "$acted" != "yes" ] && "$DIR/mediakey" "$MK" >/dev/null 2>&1
exit 0
