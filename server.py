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
}

# Everything tappable (deck buttons + every Touch Bar variant) → Mac command registry.
ACTIONS = {}
for _b in CONFIG.get("buttons", []) + CONTROL_STRIP:
    ACTIONS[_b["id"]] = _b
for _lst in APP_TOUCHBARS.values():
    for _b in _lst:
        ACTIONS[_b["id"]] = _b


def touchbar_for(app):
    """Build the Touch Bar for the frontmost app: app controls + divider + control strip."""
    items = list(APP_TOUCHBARS.get(app, []))
    if items:
        items.append({"sep": True})
    items += CONTROL_STRIP
    out = []
    for it in items:
        out.append({k: it[k] for k in ("id", "icon", "glyph", "nav", "sep", "label") if k in it})
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
}
LOCK = threading.Lock()


def frontmost_app():
    return sh("osascript -e " + json.dumps(
        'tell application "System Events" to get name of first application process whose frontmost is true'))


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
        ram = STATE["ram"]
        if tick % 2 == 0:  # RAM ~every 4s
            ram = read_ram()

        with LOCK:
            STATE.update({"battery": pct, "charging": charging, "time_left": left,
                          "net": {"down": round(down, 1), "up": round(up, 1), "ping": ping},
                          "now_playing": spot, "bt": bt, "frontmost": front, "ram": ram})
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
            payload["touchbar"] = touchbar_for(payload.get("frontmost", ""))
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
            return self._send(200, {"ok": media(body.get("cmd", ""))})
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
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"OldPhoneDeck serving on http://127.0.0.1:{PORT}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
