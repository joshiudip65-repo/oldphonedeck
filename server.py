#!/usr/bin/env python3
"""OldPhoneDeck — local Mac server. Serves the dashboard and a small JSON API.
No third-party deps (stdlib only). Binds to 127.0.0.1 only; the phone reaches it
over USB via `adb reverse`, so nothing is exposed to the network.
"""
import json, os, subprocess, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG = json.load(open(os.path.join(ROOT, "config.json")))
PORT = int(CONFIG.get("port", 8765))
BUTTONS = {b["id"]: b for b in CONFIG.get("buttons", [])}
DELL_URL = CONFIG.get("dell_url")

# Pylon ticket counter: user id from config, token read once from the Keychain.
PYLON_CFG = CONFIG.get("pylon", {})
PYLON_USER = PYLON_CFG.get("user_id", "")
PYLON_WINDOW_DAYS = int(PYLON_CFG.get("window_days", 30))
PYLON_TOKEN = ""


def keystroke_cmd(key, mods=None):
    """Shell command that sends a keystroke to the frontmost Mac app."""
    using = ""
    if mods:
        using = " using {" + ", ".join(f"{m} down" for m in mods) + "}"
    return "osascript -e " + json.dumps(f'tell application "System Events" to keystroke "{key}"{using}')


def spotify_cmd(verb):
    # guarded so it never *launches* Spotify (only acts if already running)
    return "osascript -e " + json.dumps(
        f'if application "Spotify" is running then tell application "Spotify" to {verb}')


def media_cmd(action):
    # smart media control: Spotify/Music via AppleScript, else system media key (browser)
    return f"'{os.path.join(ROOT, 'media.sh')}' {action}"


# The Control Strip (always present, right side) comes from config.json → touchbar.
CONTROL_STRIP = CONFIG.get("touchbar", [])

# App-specific Touch Bar sets — shown when that app is frontmost (real-Touch-Bar style).
APP_TOUCHBARS = {
    "Google Chrome": [
        {"id": "cr_back",   "glyph": "chevron_left",  "icon": "◀️", "exec": keystroke_cmd("[", ["command"])},
        {"id": "cr_fwd",    "glyph": "chevron_right", "icon": "▶️", "exec": keystroke_cmd("]", ["command"])},
        {"id": "cr_reload", "glyph": "reload",        "icon": "🔄", "exec": keystroke_cmd("r", ["command"])},
        {"id": "cr_newtab", "glyph": "plus",          "icon": "➕", "exec": keystroke_cmd("t", ["command"])},
        {"id": "cr_close",  "glyph": "xmark",         "icon": "✖️", "exec": keystroke_cmd("w", ["command"])},
        {"id": "cr_addr",   "glyph": "search",        "icon": "🔍", "exec": keystroke_cmd("l", ["command"])},
        {"id": "cr_mark",   "glyph": "star",          "icon": "⭐", "exec": keystroke_cmd("d", ["command"])},
    ],
    "Safari": [
        {"id": "sf_back",   "glyph": "chevron_left",  "icon": "◀️", "exec": keystroke_cmd("[", ["command"])},
        {"id": "sf_fwd",    "glyph": "chevron_right", "icon": "▶️", "exec": keystroke_cmd("]", ["command"])},
        {"id": "sf_reload", "glyph": "reload",        "icon": "🔄", "exec": keystroke_cmd("r", ["command"])},
        {"id": "sf_newtab", "glyph": "plus",          "icon": "➕", "exec": keystroke_cmd("t", ["command"])},
        {"id": "sf_addr",   "glyph": "search",        "icon": "🔍", "exec": keystroke_cmd("l", ["command"])},
    ],
    "Spotify": [
        {"id": "sp_prev",  "glyph": "backward",  "icon": "⏮", "exec": media_cmd("prev")},
        {"id": "sp_play",  "glyph": "playpause", "icon": "⏯", "exec": media_cmd("play")},
        {"id": "sp_next",  "glyph": "forward",   "icon": "⏭", "exec": media_cmd("next")},
        {"id": "sp_shuf",  "glyph": "shuffle",   "icon": "🔀", "exec": spotify_cmd("set shuffling to not shuffling")},
    ],
    "Terminal": [
        {"id": "tm_newtab", "glyph": "plus",   "icon": "➕", "exec": keystroke_cmd("t", ["command"])},
        {"id": "tm_find",   "glyph": "search", "icon": "🔍", "exec": keystroke_cmd("f", ["command"])},
        {"id": "tm_clear",  "glyph": "clear",  "icon": "🧹", "exec": keystroke_cmd("k", ["command"])},
    ],
    "Finder": [
        {"id": "fi_newfolder", "glyph": "folder_plus", "icon": "📁", "exec": keystroke_cmd("n", ["command", "shift"])},
        {"id": "fi_info",      "glyph": "info",        "icon": "ℹ️", "exec": keystroke_cmd("i", ["command"])},
        {"id": "fi_find",      "glyph": "search",      "icon": "🔍", "exec": keystroke_cmd("f", ["command"])},
    ],
    "Slack": [
        {"id": "sl_jump",   "glyph": "bolt",     "icon": "⚡", "exec": keystroke_cmd("k", ["command"])},
        {"id": "sl_search", "glyph": "search",   "icon": "🔍", "exec": keystroke_cmd("g", ["command"])},
        {"id": "sl_unread", "glyph": "envelope", "icon": "📨", "exec": keystroke_cmd("a", ["command", "shift"])},
    ],
    "Code": [
        {"id": "vs_find",    "glyph": "search",   "icon": "🔍", "exec": keystroke_cmd("f", ["command"])},
        {"id": "vs_save",    "glyph": "save",     "icon": "💾", "exec": keystroke_cmd("s", ["command"])},
        {"id": "vs_palette", "glyph": "sliders",  "icon": "🎛️", "exec": keystroke_cmd("p", ["command", "shift"])},
        {"id": "vs_term",    "glyph": "terminal", "icon": "🖥️", "exec": keystroke_cmd("`", ["control"])},
    ],
    "WhatsApp": [
        {"id": "wa_search", "glyph": "search", "icon": "🔍", "exec": keystroke_cmd("f", ["command"])},
        {"id": "wa_new",    "glyph": "pencil", "icon": "✏️", "exec": keystroke_cmd("n", ["command"])},
    ],
    # Zoom's process name is "zoom.us" when it's frontmost.
    "zoom.us": [
        {"id": "zm_mute",  "glyph": "mic",         "icon": "🎙️", "exec": keystroke_cmd("a", ["command", "shift"])},
        {"id": "zm_video", "glyph": "videocam",    "icon": "📹", "exec": keystroke_cmd("v", ["command", "shift"])},
        {"id": "zm_share", "glyph": "screenshare", "icon": "🖥️", "exec": keystroke_cmd("s", ["command", "shift"])},
        {"id": "zm_leave", "glyph": "xmark",       "icon": "✖️", "exec": keystroke_cmd("w", ["command"])},
    ],
}

# When Chrome is frontmost on a known site, show site-specific actions instead of
# the generic Chrome strip. Matched by substring against the active tab's URL.
# Actions use `open <url>` (safe/reliable) rather than single-key site shortcuts.
CHROME_SITES = {
    "atlassian.net": [  # Jira
        {"id": "jr_create", "glyph": "plus",   "icon": "➕", "exec": "open -a 'Google Chrome' 'https://varicon.atlassian.net/secure/CreateIssue!default.jspa'"},
        {"id": "jr_mine",   "glyph": "star",   "icon": "⭐", "exec": "open -a 'Google Chrome' 'https://varicon.atlassian.net/issues/?jql=assignee%3DcurrentUser()%20AND%20resolution%3DUnresolved%20ORDER%20BY%20updated%20DESC'"},
        {"id": "jr_back",   "glyph": "chevron_left", "icon": "◀️", "exec": keystroke_cmd("[", ["command"])},
        {"id": "jr_reload", "glyph": "reload", "icon": "🔄", "exec": keystroke_cmd("r", ["command"])},
    ],
    "mail.google.com": [  # Gmail
        {"id": "gm_compose", "glyph": "pencil", "icon": "✏️", "exec": "open -a 'Google Chrome' 'https://mail.google.com/mail/?view=cm&fs=1&tf=1'"},
        {"id": "gm_back",    "glyph": "chevron_left", "icon": "◀️", "exec": keystroke_cmd("[", ["command"])},
        {"id": "gm_reload",  "glyph": "reload", "icon": "🔄", "exec": keystroke_cmd("r", ["command"])},
    ],
    "meet.google.com": [  # Google Meet (shortcuts fire against the focused Meet tab)
        # Camera (Cmd+E) is omitted — the Claude Chrome extension owns that shortcut.
        {"id": "gmeet_mute",  "glyph": "mic",   "icon": "🎙️", "exec": keystroke_cmd("d", ["command"])},
        {"id": "gmeet_hand",  "glyph": "hand",  "icon": "✋", "exec": keystroke_cmd("h", ["command", "control"])},
        {"id": "gmeet_leave", "glyph": "xmark", "icon": "✖️", "exec": keystroke_cmd("w", ["command"])},
    ],
    "app.usepylon.com": [  # Pylon
        {"id": "py_reload", "glyph": "reload", "icon": "🔄", "exec": keystroke_cmd("r", ["command"])},
        {"id": "py_back",   "glyph": "chevron_left",  "icon": "◀️", "exec": keystroke_cmd("[", ["command"])},
        {"id": "py_fwd",    "glyph": "chevron_right", "icon": "▶️", "exec": keystroke_cmd("]", ["command"])},
        {"id": "py_find",   "glyph": "search", "icon": "🔍", "exec": keystroke_cmd("f", ["command"])},
    ],
}

# Everything tappable (deck buttons + every Touch Bar variant) → Mac command registry.
ACTIONS = {}
for _b in CONFIG.get("buttons", []) + CONTROL_STRIP:
    ACTIONS[_b["id"]] = _b
for _lst in list(APP_TOUCHBARS.values()) + list(CHROME_SITES.values()):
    for _b in _lst:
        ACTIONS[_b["id"]] = _b


def touchbar_for(app, playing=False, chrome_url=""):
    """Build the Touch Bar for the frontmost app: app controls + divider + control strip.

    When Chrome is on a known site, its strip is swapped for site-specific actions.
    Any play/pause button (glyph "playpause") is swapped to a concrete pause icon
    while media is playing and a play icon while it's paused/stopped."""
    app_items = APP_TOUCHBARS.get(app, [])
    if app == "Google Chrome" and chrome_url:
        for host, strip in CHROME_SITES.items():
            if host in chrome_url:
                app_items = strip
                break
    items = list(app_items)
    if items:
        items.append({"sep": True})
    items += CONTROL_STRIP
    out = []
    for it in items:
        d = {k: it[k] for k in ("id", "icon", "glyph", "nav", "sep", "label") if k in it}
        if d.get("glyph") == "playpause":
            d["glyph"] = "pause" if playing else "play"
            d["icon"] = "⏸" if playing else "▶️"
        out.append(d)
    return out
ICON_DIR = os.path.join(ROOT, ".iconcache")
os.makedirs(ICON_DIR, exist_ok=True)

# Batteries pushed in by external devices (e.g. an iPhone Shortcut): {name: (pct, ts)}
PUSHED = {}

# Shared state, refreshed by a background collector thread so API calls are instant.
STATE = {
    "mac_name": "", "battery": None, "charging": False, "time_left": "",
    "net": {"down": 0.0, "up": 0.0, "ping": None},
    "bt": [], "now_playing": None, "frontmost": "", "ram": None,
    # Optimistic play state for players we can't read (e.g. browser video on macOS 27).
    "assumed_playing": False,
    "pylon": None,  # {"new": N, "on_you": M, "open": K}
    "chrome_url": "",  # active Chrome tab URL (only read while Chrome is frontmost)
}
LOCK = threading.Lock()


def effective_playing():
    """True if media is playing. Uses Spotify/Music real state when available,
    otherwise falls back to the optimistic toggle (browser video)."""
    with LOCK:
        np = STATE.get("now_playing")
        if np is not None:
            return bool(np.get("playing"))
        return bool(STATE.get("assumed_playing"))


def register_playpause():
    """Called right after a play/pause press. Re-reads the real player if one is
    running (Spotify/Music), else flips the optimistic browser toggle."""
    spot = read_spotify()
    with LOCK:
        if spot is not None:
            STATE["now_playing"] = spot
            STATE["assumed_playing"] = bool(spot.get("playing"))
        else:
            STATE["assumed_playing"] = not STATE.get("assumed_playing", False)


def frontmost_app():
    return sh("osascript -e " + json.dumps(
        'tell application "System Events" to get name of first application process whose frontmost is true'))


def read_chrome_url():
    """Active tab URL of the front Chrome window (empty if none / not permitted)."""
    return sh("osascript -e " + json.dumps(
        'tell application "Google Chrome" to if (count of windows) > 0 '
        'then return URL of active tab of front window'))


def read_ram():
    try:
        total = int(sh("sysctl -n hw.memsize"))
    except (TypeError, ValueError):
        return None
    import re
    vm = sh("vm_stat")
    pagesize = 4096
    pages = {}
    for line in vm.splitlines():
        ps = re.search(r"page size of (\d+) bytes", line)
        if ps:
            pagesize = int(ps.group(1))
        if ":" in line:
            k, v = line.split(":", 1)
            v = v.strip().rstrip(".")
            if v.isdigit():
                pages[k.strip()] = int(v)
    used = (pages.get("Pages active", 0) + pages.get("Pages wired down", 0)
            + pages.get("Pages occupied by compressor", 0)) * pagesize
    return {"used_gb": round(used / 1e9, 1), "total_gb": round(total / 1e9, 1),
            "percent": round(used / total * 100)}


def sh(cmd, timeout=6):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True,
                              text=True, timeout=timeout).stdout.strip()
    except Exception:
        return ""


def app_path(app_name):
    p = f"/Applications/{app_name}.app"
    if os.path.isdir(p):
        return p
    r = sh(f"mdfind \"kMDItemKind == 'Application'\" 2>/dev/null | grep -iE '/{app_name}.app$' | head -1")
    return r if r and os.path.isdir(r) else None


def mac_app_png(app_dir, out):
    """Render a Mac .app's icon to a 128px PNG at `out`. Returns out or None."""
    icon = sh(f"/usr/libexec/PlistBuddy -c 'Print :CFBundleIconFile' '{app_dir}/Contents/Info.plist' 2>/dev/null")
    if icon and not icon.endswith(".icns"):
        icon += ".icns"
    icns = os.path.join(app_dir, "Contents", "Resources", icon) if icon else ""
    if not (icns and os.path.isfile(icns)):
        icns = sh(f"ls '{app_dir}/Contents/Resources/'*.icns 2>/dev/null | head -1")
    if icns and os.path.isfile(icns):
        sh(f"sips -s format png -Z 128 '{icns}' --out '{out}' >/dev/null 2>&1")
        if os.path.isfile(out):
            return out
    return None


def app_icon_by_name(name):
    """Icon PNG for an arbitrary running app, cached by name."""
    import re
    safe = re.sub(r"[^A-Za-z0-9]+", "_", name)
    out = os.path.join(ICON_DIR, f"app_{safe}.png")
    if os.path.isfile(out) and os.path.getsize(out) > 0:
        return out
    ap = app_path(name)
    return mac_app_png(ap, out) if ap else None


def build_icon(btn):
    """Return a path to a 128px PNG for this button, building/caching it once."""
    out = os.path.join(ICON_DIR, f"{btn['id']}.png")
    if os.path.isfile(out) and os.path.getsize(out) > 0:
        return out

    app = btn.get("app")
    if app:
        ap = app_path(app)
        if ap and mac_app_png(ap, out):
            return out

    url = btn.get("icon_url")
    if url:
        tmp = out + ".src"
        # curl uses the system cert store (Python.org build can't verify TLS certs)
        sh(f"curl -sL -A 'Mozilla/5.0' --max-time 8 '{url}' -o '{tmp}'")
        if os.path.isfile(tmp) and os.path.getsize(tmp) > 0:
            sh(f"sips -s format png -Z 128 '{tmp}' --out '{out}' >/dev/null 2>&1")
            if os.path.isfile(out):
                os.remove(tmp)
                return out
            os.replace(tmp, out)  # sips failed; assume already a usable image
            return out
    return None


def default_iface():
    return sh("route get default 2>/dev/null | awk '/interface:/{print $2}'") or "en0"


def net_counters(iface):
    out = sh(f"netstat -I {iface} -b 2>/dev/null")
    for line in out.splitlines():
        p = line.split()
        if len(p) >= 10 and p[0] == iface and "Link" in line:
            try:
                return int(p[6]), int(p[9])
            except ValueError:
                pass
    return None


def read_battery():
    out = sh("pmset -g batt")
    charging = "AC Power" in out
    pct, left = None, ""
    for line in out.splitlines():
        if "InternalBattery" in line:
            parts = line.split("\t")[-1].split(";")
            try:
                pct = int(parts[0].strip().rstrip("%"))
            except Exception:
                pass
            for seg in parts:
                seg = seg.strip()
                if "remaining" in seg:
                    left = seg.split(" ")[0]
    return pct, charging, left


def read_spotify():
    scr = ('tell application "System Events" to set ok to (exists process "Spotify")\n'
           'if ok then tell application "Spotify"\n'
           'set s to player state as string\n'
           'if s is not "stopped" then\n'
           'return (name of current track) & "\\t" & (artist of current track) & "\\t" & s '
           '& "\\t" & (player position) & "\\t" & (duration of current track)\n'
           'end if\nend if\nreturn ""')
    out = sh("osascript " + " ".join(f"-e {json.dumps(l)}" for l in scr.split("\n")))
    if not out:
        return None
    f = out.split("\t")
    if len(f) < 5:
        return None
    try:
        pos, dur = float(f[3]), float(f[4]) / 1000.0
    except ValueError:
        pos, dur = 0, 0
    return {"track": f[0], "artist": f[1], "playing": f[2] == "playing",
            "pos": pos, "dur": dur}


def read_hid_batteries():
    """Apple HID peripherals (Magic Mouse / Trackpad / Keyboard) report here."""
    out = []
    txt = sh("ioreg -r -k BatteryPercent -d 1 2>/dev/null")
    name = None
    for line in txt.splitlines():
        if '"Product"' in line:
            name = line.split("=", 1)[-1].strip().strip('"')
        elif '"BatteryPercent"' in line:
            try:
                pct = int(line.split("=", 1)[-1].strip())
            except ValueError:
                continue
            out.append({"name": clean_name(name or "Device"), "pct": pct})
            name = None
    return out


def clean_name(name):
    import re
    name = re.sub(r"^[^']+'s\s+", "", name)   # drop "Udip's " owner prefix
    name = re.sub(r"\s*\d+$", "", name)         # drop trailing model number "2"
    return name.strip() or "Device"


_DELL_CACHE = {"val": None, "ts": 0.0}


def read_dell():
    """Dell Latitude status dashboard on the LAN. Caches last good value to avoid flicker."""
    if not DELL_URL:
        return None
    try:
        with urllib.request.urlopen(DELL_URL, timeout=3) as r:
            d = json.loads(r.read().decode())
        val = {"name": "Dell Latitude", "status": "Connected" if bool(d.get("ac")) else "No"}
        _DELL_CACHE["val"] = val
        _DELL_CACHE["ts"] = time.time()
        return val
    except Exception:
        if _DELL_CACHE["val"] and time.time() - _DELL_CACHE["ts"] < 120:
            return _DELL_CACHE["val"]
        return None


def pushed_devices():
    """External batteries pushed via /api/push, kept for 15 min."""
    now = time.time()
    out = []
    for name, (pct, ts) in list(PUSHED.items()):
        if now - ts < 900:
            out.append({"name": name, "pct": int(pct)})
        else:
            PUSHED.pop(name, None)
    return out


def build_devices():
    devices = []
    devices += read_hid_batteries()      # Magic Mouse, etc.
    devices += pushed_devices()          # iPhone (if a Shortcut pushes it)
    dell = read_dell()
    if dell:
        devices.append(dell)
    # de-dup by name, cap for layout
    seen, res = set(), []
    for d in devices:
        if d["name"] not in seen:
            seen.add(d["name"]); res.append(d)
    return res[:5]


def read_pylon():
    """Count tickets assigned to Udip over the recent window: open (not closed)
    and 'waiting on you'. Paginates the issues list and filters client-side
    (the API has no assignee filter). Returns {"waiting": N, "open": M} or None."""
    if not (PYLON_TOKEN and PYLON_USER):
        return None
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=PYLON_WINDOW_DAYS)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    base = ("https://api.usepylon.com/issues"
            f"?start_time={start.strftime(fmt)}&end_time={now.strftime(fmt)}&limit=100")
    hdr = json.dumps("Authorization: Bearer " + PYLON_TOKEN)
    new_all = on_you = openc = 0
    cursor = None
    for _ in range(25):  # cap pages so a refresh can't run away
        url = base + (f"&cursor={cursor}" if cursor else "")
        out = sh(f"curl -s --max-time 15 -H {hdr} {json.dumps(url)}", timeout=20)
        try:
            d = json.loads(out)
        except Exception:
            break
        for i in d.get("data", []):
            st = i.get("state")
            a = i.get("assignee") or {}
            aid = a.get("id") if isinstance(a, dict) else None
            if st == "new":
                new_all += 1          # whole incoming queue, regardless of assignee
            if aid != PYLON_USER:
                continue
            if st == "closed":
                continue
            openc += 1                # everything of mine that isn't closed
            if st == "waiting_on_you":
                on_you += 1           # my tickets where the ball is in my court
        pg = d.get("pagination") or {}
        if not pg.get("has_next_page"):
            break
        cursor = pg.get("cursor")
    return {"new": new_all, "on_you": on_you, "open": openc}


def pylon_collector():
    """Refresh the Pylon ticket counts every ~5 minutes (own thread; the scan
    makes many sequential API calls and must not stall the 2s state loop)."""
    global PYLON_TOKEN
    PYLON_TOKEN = sh("security find-generic-password -s pylon-api-token -w") or ""
    while True:
        try:
            counts = read_pylon()
        except Exception:
            counts = None
        if counts is not None:
            with LOCK:
                STATE["pylon"] = counts
        time.sleep(300)


def collector():
    iface = default_iface()
    name = sh("scutil --get ComputerName") or "Mac"
    prev = net_counters(iface); prev_t = time.time()
    tick = 0
    with LOCK:
        STATE["mac_name"] = name
    while True:
        tick += 1
        now = time.time()
        cur = net_counters(iface)
        down = up = 0.0
        dt = now - prev_t
        if cur and prev and dt >= 0.5:  # skip first tick / tiny gaps → avoids bogus spikes
            down = max(0.0, (cur[0] - prev[0]) * 8 / 1e6 / dt)  # Mbps
            up = max(0.0, (cur[1] - prev[1]) * 8 / 1e6 / dt)
            prev, prev_t = cur, now
        elif prev is None:
            prev, prev_t = cur, now

        pct, charging, left = read_battery()
        spot = read_spotify()
        ping = STATE["net"].get("ping")
        if tick % 3 == 0:  # ping every ~6s
            p = sh("ping -c1 -t1 1.1.1.1 2>/dev/null | awk -F'time=' '/time=/{print $2}' | awk '{print $1}'")
            try:
                ping = round(float(p))
            except Exception:
                ping = None
        bt = STATE["bt"]
        if tick % 4 == 1:  # refresh device batteries ~every 8s (mouse + Dell over LAN)
            bt = build_devices()

        front = frontmost_app()
        chrome_url = read_chrome_url() if front == "Google Chrome" else ""
        ram = STATE["ram"]
        if tick % 2 == 0:  # RAM ~every 4s
            ram = read_ram()

        with LOCK:
            STATE.update({"battery": pct, "charging": charging, "time_left": left,
                          "net": {"down": round(down, 1), "up": round(up, 1), "ping": ping},
                          "now_playing": spot, "bt": bt, "frontmost": front, "ram": ram,
                          "chrome_url": chrome_url})
        time.sleep(2)


def running_apps():
    """GUI apps the user has open (foreground, non-background processes)."""
    scr = ('tell application "System Events" to get name of '
           '(every process whose background only is false)')
    out = sh("osascript -e " + json.dumps(scr))
    skip = {"oldphonedeck", "Python"}
    names = sorted({n.strip() for n in out.split(",") if n.strip() and n.strip() not in skip},
                   key=str.lower)
    return [{"name": n} for n in names]


def quit_app(name, force=False):
    safe = name.replace('"', "")
    if force:
        sh(f'pkill -x {json.dumps(safe)}')
    else:
        sh("osascript -e " + json.dumps(f'tell application "{safe}" to quit'))
    return True


def media(cmd):
    if cmd in ("play", "next", "prev"):
        sh(media_cmd(cmd))
        return True
    return False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/stats":
            with LOCK:
                payload = dict(STATE)
            payload["buttons"] = CONFIG.get("buttons", [])
            payload["touchbar"] = touchbar_for(payload.get("frontmost", ""), effective_playing(),
                                               payload.get("chrome_url", ""))
            payload["dashboard_url"] = CONFIG.get("dashboard_url", "")
            try:
                payload["transport"] = open(os.path.join(ROOT, ".transport")).read().strip()
            except Exception:
                payload["transport"] = ""
            return self._send(200, payload)
        if path == "/api/apps":
            return self._send(200, {"apps": running_apps()})
        if path == "/api/icon":
            from urllib.parse import urlparse, parse_qs
            bid = (parse_qs(urlparse(self.path).query).get("id") or [""])[0]
            btn = BUTTONS.get(bid)
            fp = build_icon(btn) if btn else None
            if fp and os.path.isfile(fp):
                with open(fp, "rb") as f:
                    return self._send(200, f.read(), "image/png")
            return self._send(404, {"error": "no icon"})
        if path == "/api/appicon":
            from urllib.parse import urlparse, parse_qs
            name = (parse_qs(urlparse(self.path).query).get("name") or [""])[0]
            fp = app_icon_by_name(name) if name else None
            if fp and os.path.isfile(fp):
                with open(fp, "rb") as f:
                    return self._send(200, f.read(), "image/png")
            return self._send(404, {"error": "no icon"})
        # static files
        rel = "index.html" if path == "/" else path.lstrip("/")
        fp = os.path.normpath(os.path.join(ROOT, "static", rel))
        if not fp.startswith(os.path.join(ROOT, "static")) or not os.path.isfile(fp):
            return self._send(404, {"error": "not found"})
        ctype = ("text/html" if fp.endswith(".html") else "text/css" if fp.endswith(".css")
                 else "application/javascript" if fp.endswith(".js") else "application/octet-stream")
        with open(fp, "rb") as f:
            return self._send(200, f.read(), ctype)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            body = {}
        if self.path == "/api/action":
            act = ACTIONS.get(body.get("id"))
            if act and act.get("exec"):
                if act.get("glyph") == "playpause":
                    # run synchronously so we can read back the new play state at once
                    try:
                        subprocess.run(act["exec"], shell=True, timeout=6)
                    except Exception:
                        pass
                    register_playpause()
                else:
                    subprocess.Popen(act["exec"], shell=True)
                return self._send(200, {"ok": True})
            return self._send(400, {"ok": False})
        if self.path == "/api/type":
            text = body.get("text", "")
            if text:
                try:
                    subprocess.run(["pbcopy"], input=text, text=True, timeout=3)
                except Exception:
                    pass
                sh("osascript -e " + json.dumps(
                    'tell application "System Events" to keystroke "v" using command down'))
                return self._send(200, {"ok": True})
            return self._send(400, {"ok": False})
        if self.path == "/api/quit":
            name = body.get("name")
            if name:
                quit_app(name, bool(body.get("force")))
                return self._send(200, {"ok": True})
            return self._send(400, {"ok": False})
        if self.path == "/api/media":
            cmd = body.get("cmd", "")
            ok = media(cmd)
            if ok and cmd == "play":
                register_playpause()
            return self._send(200, {"ok": ok})
        if self.path == "/api/push":
            name = body.get("source") or body.get("name")
            pct = body.get("pct")
            if name and pct is not None:
                PUSHED[str(name)] = (float(pct), time.time())
                return self._send(200, {"ok": True})
            return self._send(400, {"ok": False})
        return self._send(404, {"error": "not found"})


def main():
    threading.Thread(target=collector, daemon=True).start()
    threading.Thread(target=pylon_collector, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"OldPhoneDeck serving on http://127.0.0.1:{PORT}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
