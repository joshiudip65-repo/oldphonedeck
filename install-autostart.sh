#!/bin/bash
# Installs the OldPhoneDeck watcher as a launchd agent so the deck auto-launches
# whenever you plug the phone in (and survives logout/reboot).
set -e
DIR="$HOME/oldphonedeck"
LABEL="com.oldphonedeck.watcher"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

mkdir -p "$HOME/Library/LaunchAgents"
sed "s#__DIR__#$DIR#g" "$DIR/com.oldphonedeck.watcher.plist" > "$PLIST"

# reload cleanly
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/$LABEL"

echo "Installed. Watcher is live — plug in the phone and the deck launches itself."
echo "Logs: $DIR/watcher.log"
echo "To stop:   launchctl bootout gui/$(id -u)/$LABEL"
