# OldPhoneDeck

Turn the Samsung Galaxy S20+ into a USB-powered "deck" for the Mac — a fullscreen
dashboard of app-launcher buttons and live Mac widgets (internet speed, batteries,
Spotify now-playing). Runs **entirely over the USB cable** (no Wi-Fi) and
**auto-launches the moment you plug the phone in.**

## How it works

```
 ┌─────────────┐   USB cable (adb reverse)   ┌──────────────────┐
 │  S20+ app   │ ──────────────────────────► │  Mac helper      │
 │ (native APK)│   http://localhost:8790     │  server.py       │
 │  the "face" │ ◄────────────────────────── │  the "brain"     │
 └─────────────┘   stats + actions           └──────────────────┘
```

- **server.py** — tiny stdlib Python server on the Mac (127.0.0.1 only). Reports
  battery, network throughput, Bluetooth batteries, and Spotify now-playing; runs
  Mac actions (open apps, media controls). Nothing is exposed to the network.
- **android/** — native Kotlin app. Polls the helper every 2s and renders the deck.
  Buttons and now-playing controls POST back to the helper.
- **adb reverse** — maps the phone's `localhost:8790` to the Mac over USB.
- **watch.sh + launchd** — detects the phone attaching and runs `connect.sh`
  (start helper → open tunnel → keep screen awake → launch the app).

## Install the auto-start

```bash
bash ~/oldphonedeck/install-autostart.sh
```

After that, just plug the phone in — the deck launches itself. (Keep the phone
**unlocked / set to no lock** for a dock device, or it sits behind the lock screen.)

## Customise the buttons

Edit `config.json` → `buttons`. Each entry: `id`, `label`, `icon` (emoji), and
`exec` (any Mac shell command). Changes are picked up on the next helper restart;
the app reloads the button list automatically.

## Rebuild the APK

```bash
cd ~/oldphonedeck/android
JAVA_HOME=/opt/homebrew/opt/openjdk@17 ./gradlew :app:assembleDebug
adb -s YOUR_PHONE_SERIAL install -r app/build/outputs/apk/debug/app-debug.apk
```

## Manual run (no auto-start)

```bash
bash ~/oldphonedeck/connect.sh
```

## Notes

- Port is **8790** (8765 was taken by the NEPSE dashboard).
- Target phone serial is pinned in `config.json` (`YOUR_PHONE_SERIAL`).
- Bluetooth battery levels only show for devices that report them to macOS.
