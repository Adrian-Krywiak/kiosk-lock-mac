"""kiosklock command line.

  python3 -m kiosklock set-password
  python3 -m kiosklock lock https://docs.python.org --minutes 50 --message "Finish the assignment"
  python3 -m kiosklock lock https://leetcode.com --until 17:00 --allow leetcode.com github.com
  python3 -m kiosklock lock https://en.wikipedia.org --test 20
  python3 -m kiosklock status
  python3 -m kiosklock install | uninstall
"""

import argparse
import getpass
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from . import store

LABEL = "com.kiosklock.agent"
PLIST = Path.home() / "Library" / "LaunchAgents" / (LABEL + ".plist")
REPO = Path(__file__).resolve().parent.parent

PLIST_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>-m</string>
        <string>kiosklock</string>
        <string>run</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{repo}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONPATH</key>
        <string>{repo}</string>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
    </dict>
    <!-- Start at login. If there's no active lock, `run` exits right away. -->
    <key>RunAtLoad</key>
    <true/>
    <!-- Restart only if it was killed: a normal unlock exits 0 and stays off. -->
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>ThrottleInterval</key>
    <integer>3</integer>
    <key>ProcessType</key>
    <string>Interactive</string>
    <key>StandardOutPath</key>
    <string>{logs}/kiosklock.log</string>
    <key>StandardErrorPath</key>
    <string>{logs}/kiosklock.log</string>
</dict>
</plist>
"""


def _domain():
    return "gui/%d" % os.getuid()


def agent_loaded():
    return subprocess.run(
        ["launchctl", "print", "%s/%s" % (_domain(), LABEL)], capture_output=True
    ).returncode == 0


def _default_host(url):
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _until(args):
    if args.until:
        hour, minute = (int(x) for x in args.until.split(":"))
        target = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= datetime.now():
            target += timedelta(days=1)
        return target.timestamp()
    return time.time() + args.minutes * 60


# --- commands -------------------------------------------------------------------

def cmd_set_password(args):
    print("Have your friend type this. Don't watch. Only a hash is saved.")
    first = getpass.getpass("New unlock password: ")
    if len(first) < 6:
        sys.exit("Use at least 6 characters.")
    if getpass.getpass("Type it again: ") != first:
        sys.exit("They didn't match. Nothing was changed.")
    store.set_password(first)
    print("Saved.")


def cmd_lock(args):
    url = args.url if "://" in args.url else "https://" + args.url
    allowed = [h.lower() for h in (args.allow or [_default_host(url)])]
    message = args.message or "Focus time"

    if args.test is not None:
        now = time.time()
        lock = {"url": url, "allowed_hosts": allowed, "until": now + args.test,
                "started": now, "message": message}
        from . import app
        app.run(lock, test_seconds=args.test)
        return

    if args.minutes is None and not args.until:
        sys.exit("Say how long: --minutes 45 or --until 17:00 (or --test 20 to try it).")
    if not store.has_password():
        sys.exit("Set the friend password first: python3 -m kiosklock set-password")
    if store.active_lock():
        sys.exit("A lock is already running.")

    until = _until(args)
    store.save_lock(url, allowed, until, message)
    when = datetime.fromtimestamp(until).strftime("%H:%M")
    if agent_loaded():
        subprocess.run(["launchctl", "kickstart", "%s/%s" % (_domain(), LABEL)], check=False)
        print("Locked until %s." % when)
    else:
        print("Locked until %s. (Agent not installed, so killing this process ends the lock early."
              " Run `python3 -m kiosklock install` to make it come back.)" % when)
        from . import app
        app.run(store.active_lock())


def cmd_run(args):
    lock = store.active_lock()
    if lock is None:
        store.clear_lock()
        return
    from . import app
    app.run(lock)


def cmd_status(args):
    lock = store.active_lock()
    if lock:
        left = int(lock["until"] - time.time())
        print("Locked: %s (%d min %02d s left), allowed: %s"
              % (lock["url"], left // 60, left % 60, ", ".join(lock["allowed_hosts"])))
    else:
        print("Not locked.")
    print("Friend password: %s" % ("set" if store.has_password() else "not set"))
    print("Agent: %s" % ("installed" if agent_loaded() else "not installed"))


def cmd_install(args):
    logs = store.HOME / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    PLIST.write_text(PLIST_TEMPLATE.format(label=LABEL, python=sys.executable, repo=REPO, logs=logs))
    subprocess.run(["launchctl", "bootout", "%s/%s" % (_domain(), LABEL)], capture_output=True)
    subprocess.run(["launchctl", "bootstrap", _domain(), str(PLIST)], check=True)
    print("Installed. Locks now survive being killed and come back after a restart until they end.")
    print("To make it hard to undo, have your friend follow HARDENING.md.")


def cmd_uninstall(args):
    if store.active_lock():
        sys.exit("Can't uninstall during a lock.")
    subprocess.run(["launchctl", "bootout", "%s/%s" % (_domain(), LABEL)], capture_output=True)
    PLIST.unlink(missing_ok=True)
    print("Uninstalled.")


def main(argv=None):
    p = argparse.ArgumentParser(prog="kiosklock", description="Lock your Mac to one website until a timer runs out.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("set-password", help="set the friend-held early-unlock password").set_defaults(fn=cmd_set_password)

    lk = sub.add_parser("lock", help="start a lock")
    lk.add_argument("url", help="the page to open, e.g. https://leetcode.com")
    lk.add_argument("--allow", nargs="+", metavar="HOST",
                    help="hosts you may navigate to (default: the URL's host); subdomains count")
    when = lk.add_mutually_exclusive_group()
    when.add_argument("--minutes", type=float, help="lock for this many minutes")
    when.add_argument("--until", metavar="HH:MM", help="lock until this time (24h)")
    when.add_argument("--test", type=int, nargs="?", const=20, metavar="SECONDS",
                      help="try it: the real lock, released after SECONDS (default 20), nothing saved")
    lk.add_argument("--message", help="what the sidebar says, e.g. 'Finish the essay'")
    lk.set_defaults(fn=cmd_lock)

    sub.add_parser("run", help="used by the LaunchAgent: resume an active lock").set_defaults(fn=cmd_run)
    sub.add_parser("status", help="show the current lock").set_defaults(fn=cmd_status)
    sub.add_parser("install", help="install the LaunchAgent").set_defaults(fn=cmd_install)
    sub.add_parser("uninstall", help="remove the LaunchAgent").set_defaults(fn=cmd_uninstall)

    args = p.parse_args(argv)
    args.fn(args)
