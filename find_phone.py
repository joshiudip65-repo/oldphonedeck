#!/usr/bin/env python3
"""Find the phone's wireless-adb endpoint on the LAN (self-heals DHCP changes).
Scans the Mac's /24 for the wireless_port, then verifies the adb serial matches
the target phone. Prints "ip:port" if found, nothing otherwise."""
import json, os, socket, subprocess, sys
import concurrent.futures as cf

ROOT = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(ROOT, "config.json")))
SERIAL = CFG.get("target_serial", "")
PORT = int(CFG.get("wireless_port", 5555))
ADB = "/opt/homebrew/bin/adb"


def my_subnet():
    out = subprocess.run("ipconfig getifaddr en0", shell=True,
                         capture_output=True, text=True).stdout.strip()
    return out.rsplit(".", 1)[0] + "." if out else None


def port_open(ip):
    s = socket.socket()
    s.settimeout(0.3)
    try:
        return ip if s.connect_ex((ip, PORT)) == 0 else None
    except Exception:
        return None
    finally:
        s.close()


def serial_of(dev):
    try:
        subprocess.run([ADB, "connect", dev], capture_output=True, timeout=5)
        r = subprocess.run([ADB, "-s", dev, "shell", "getprop", "ro.serialno"],
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip()
    except Exception:
        return ""


def main():
    sub = my_subnet()
    if not sub:
        return
    hosts = [sub + str(i) for i in range(1, 255)]
    cands = []
    with cf.ThreadPoolExecutor(max_workers=256) as ex:
        for r in ex.map(port_open, hosts):
            if r:
                cands.append(r)
    for ip in cands:
        dev = f"{ip}:{PORT}"
        if serial_of(dev) == SERIAL and SERIAL:
            print(dev)
            return


if __name__ == "__main__":
    main()
