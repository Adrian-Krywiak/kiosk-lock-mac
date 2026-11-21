"""Runs a lock: shows it, keeps it in front, and ends it on time or on the password."""

import json
import signal
import sys
import time
from datetime import datetime

import objc
from AppKit import NSApplication
from Foundation import NSObject, NSTimer
from PyObjCTools import AppHelper

from . import sidebar, store
from .lockscreen import LockScreen

TICK = 1.0  # seconds between "stay in front / time up?" checks


def log(msg):
    print("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg), flush=True)


class _Delegate(NSObject):
    def initWithRunner_(self, runner):
        self = objc.super(_Delegate, self).init()
        if self is None:
            return None
        self._runner = runner
        return self

    def applicationShouldTerminate_(self, sender):
        # Refuse to quit while locked (NSTerminateCancel), otherwise allow it
        return 0 if self._runner.screen.visible else 1

    def tick_(self, timer):
        self._runner.tick()


class Runner(object):
    """lock: dict with url, allowed_hosts, until, started, message.
    test_seconds: release after this many seconds no matter what (nothing saved)."""

    def __init__(self, lock, test_seconds=None):
        self.lock = lock
        self.test = test_seconds is not None
        self.screen = LockScreen(lock["allowed_hosts"], on_message=self.on_message)
        self._delegate = None

    def start(self):
        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(1)
        self._delegate = _Delegate.alloc().initWithRunner_(self)
        app.setDelegate_(self._delegate)
        if not self.test:
            # A plain `kill` shouldn't end it; the LaunchAgent restarts it after SIGKILL anyway
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
        self.screen.show(self.lock["url"], sidebar.render(self.lock, self._test_seconds()))
        log("locked until %s" % datetime.fromtimestamp(self.lock["until"]).strftime("%H:%M:%S"))
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            TICK, self._delegate, "tick:", None, True
        )
        AppHelper.runEventLoop(installInterrupt=self.test)

    def _test_seconds(self):
        return int(round(self.lock["until"] - self.lock["started"])) if self.test else None

    def tick(self):
        if time.time() >= self.lock["until"]:
            self.finish("time is up")
        else:
            self.screen.raise_to_front()

    def finish(self, why):
        log("unlocked: %s" % why)
        if not self.test:
            store.clear_lock()
        self.screen.hide()
        AppHelper.stopEventLoop()

    def on_message(self, data):
        action = data.get("action")
        if action == "open":
            self.screen.navigate(data.get("url") or "")
        elif action == "prompt":
            self.screen.focus_sidebar()
        elif action == "cancel":
            self.screen.focus_web()
        elif action == "unlock":
            if not store.has_password():
                self.screen.sidebar_js("showError(%s)" % json.dumps("No password is set, so there's no early exit."))
            elif store.check_password(data.get("password") or ""):
                self.finish("friend password")
            else:
                log("wrong password")
                self.screen.sidebar_js("showError(%s)" % json.dumps("That isn't the password."))


def run(lock, test_seconds=None):
    Runner(lock, test_seconds).start()
    sys.exit(0)
