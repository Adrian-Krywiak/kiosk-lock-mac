"""The shield: full-screen windows on every display, one website, nothing else.

LockScreen is usable on its own. It draws an optional sidebar (your HTML) next
to a web view that can only navigate to the hosts you allow, hides the Dock and
menu bar, blocks app switching and Force Quit, and swallows the shortcuts that
would close or hide it. The sidebar talks back through
window.webkit.messageHandlers.kiosklock.postMessage({...}).
"""

import objc
from AppKit import (
    NSApp,
    NSApplication,
    NSBackingStoreBuffered,
    NSColor,
    NSEvent,
    NSMakeRect,
    NSScreen,
    NSView,
    NSWindow,
)
from Foundation import NSObject, NSURL, NSURLRequest
from Quartz import CGShieldingWindowLevel
from WebKit import WKUserContentController, WKWebView, WKWebViewConfiguration

# NSApplicationPresentationOptions
HIDE_DOCK = 1 << 1
HIDE_MENU_BAR = 1 << 3
DISABLE_PROCESS_SWITCHING = 1 << 5
DISABLE_FORCE_QUIT = 1 << 6
DISABLE_SESSION_TERMINATION = 1 << 7
DISABLE_HIDE_APPLICATION = 1 << 8
KIOSK = (
    HIDE_DOCK
    | HIDE_MENU_BAR
    | DISABLE_PROCESS_SWITCHING
    | DISABLE_FORCE_QUIT
    | DISABLE_SESSION_TERMINATION
    | DISABLE_HIDE_APPLICATION
)

# NSWindowCollectionBehavior
CB_ALL_SPACES = 1 << 0
CB_STATIONARY = 1 << 4
CB_IGNORES_CYCLE = 1 << 6
CB_FULLSCREEN_AUX = 1 << 8

NS_EVENT_MASK_KEY_DOWN = 1 << 10
NS_CMD = 1 << 20

WK_ALLOW, WK_CANCEL = 1, 0
HANDLER = "kiosklock"

# A bare WKWebView reports "...AppleWebKit/605.1.15 (KHTML, like Gecko)" with no
# Safari token, which some sign-in pages reject as an embedded browser.
SAFARI_UA_SUFFIX = "Version/26.0 Safari/605.1.15"


def host_allowed(host, allowed):
    """True for an allowed host or any of its subdomains."""
    host = (host or "").lower()
    return any(host == h or host.endswith("." + h) for h in allowed)


class _LockWindow(NSWindow):
    """A borderless window refuses key status by default, which would leave the
    web view unable to receive a single keystroke. Opt back in."""

    def canBecomeKeyWindow(self):
        return True

    def canBecomeMainWindow(self):
        return True


class _Bridge(NSObject):
    """Navigation policy, popups, and messages from the sidebar."""

    def initWithOwner_(self, owner):
        self = objc.super(_Bridge, self).init()
        if self is None:
            return None
        self._owner = owner
        return self

    # WKNavigationDelegate: only top-level navigation is gated, so pages still
    # load their scripts, images and iframes from wherever they need to.
    def webView_decidePolicyForNavigationAction_decisionHandler_(self, webview, action, handler):
        frame = action.targetFrame()
        if frame is not None and not frame.isMainFrame():
            handler(WK_ALLOW)
            return
        url = action.request().URL()
        if url is None or host_allowed(url.host(), self._owner.allowed_hosts):
            handler(WK_ALLOW)
        else:
            handler(WK_CANCEL)

    # WKUIDelegate: links that open a new window load in place instead (when allowed)
    def webView_createWebViewWithConfiguration_forNavigationAction_windowFeatures_(
        self, webview, configuration, action, features
    ):
        url = action.request().URL()
        if url is not None and host_allowed(url.host(), self._owner.allowed_hosts):
            webview.loadRequest_(action.request())
        return None

    # WKScriptMessageHandler
    def userContentController_didReceiveScriptMessage_(self, controller, message):
        body = message.body()
        try:
            data = {str(k): (str(body[k]) if body[k] is not None else None) for k in body}
        except TypeError:
            return
        self._owner.on_message(data)


class LockScreen(object):
    """Owns the shield windows. Safe to show() and hide() repeatedly.

    allowed_hosts: hosts the main web view may navigate to (subdomains included)
    on_message:    called with a dict for every postMessage from the sidebar
    """

    def __init__(self, allowed_hosts, on_message=None, sidebar_width=340.0):
        self.allowed_hosts = tuple(h.lower() for h in allowed_hosts)
        self._on_message = on_message or (lambda data: None)
        self.sidebar_width = float(sidebar_width)
        self.visible = False
        self._windows = []
        self._sidebar = None
        self._web = None
        self._bridge = None
        self._monitor = None

    # --- lifecycle --------------------------------------------------------

    def show(self, start_url, sidebar_html=None):
        if self.visible:
            return
        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(0)  # Regular: needed to own the foreground
        self._bridge = _Bridge.alloc().initWithOwner_(self)

        for index, screen in enumerate(NSScreen.screens()):
            win = self._make_window(screen)
            if index == 0:
                self._install_panes(win, start_url, sidebar_html)
            self._windows.append(win)
            win.makeKeyAndOrderFront_(None)

        app.setPresentationOptions_(KIOSK)
        self._monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            NS_EVENT_MASK_KEY_DOWN, self._swallow_shortcuts
        )
        self.visible = True
        self.raise_to_front()

    def hide(self):
        if not self.visible:
            return
        if self._monitor is not None:
            NSEvent.removeMonitor_(self._monitor)
            self._monitor = None
        for win in self._windows:
            win.orderOut_(None)
            win.close()
        self._windows = []
        self._sidebar = self._web = self._bridge = None
        app = NSApplication.sharedApplication()
        app.setPresentationOptions_(0)
        app.setActivationPolicy_(1)  # Accessory: no Dock icon while unlocked
        self.visible = False

    def _make_window(self, screen):
        win = _LockWindow.alloc().initWithContentRect_styleMask_backing_defer_screen_(
            screen.frame(), 0, NSBackingStoreBuffered, False, screen
        )
        win.setLevel_(CGShieldingWindowLevel())
        win.setOpaque_(True)
        win.setBackgroundColor_(NSColor.colorWithCalibratedWhite_alpha_(0.043, 1.0))
        win.setCollectionBehavior_(CB_ALL_SPACES | CB_STATIONARY | CB_IGNORES_CYCLE | CB_FULLSCREEN_AUX)
        win.setHidesOnDeactivate_(False)
        win.setReleasedWhenClosed_(False)
        win.setAcceptsMouseMovedEvents_(True)
        return win

    def _install_panes(self, win, start_url, sidebar_html):
        bounds = win.contentView().bounds()
        w, h = bounds.size.width, bounds.size.height
        side = self.sidebar_width if sidebar_html else 0.0
        content = win.contentView()

        if sidebar_html:
            config = WKWebViewConfiguration.alloc().init()
            controller = WKUserContentController.alloc().init()
            controller.addScriptMessageHandler_name_(self._bridge, HANDLER)
            config.setUserContentController_(controller)
            self._sidebar = WKWebView.alloc().initWithFrame_configuration_(NSMakeRect(0, 0, side, h), config)
            self._sidebar.setAutoresizingMask_(16 | 4)  # height sizable, pinned left
            self._sidebar.loadHTMLString_baseURL_(sidebar_html, None)
            content.addSubview_(self._sidebar)

            divider = NSView.alloc().initWithFrame_(NSMakeRect(side - 1, 0, 1, h))
            divider.setWantsLayer_(True)
            divider.layer().setBackgroundColor_(NSColor.colorWithCalibratedWhite_alpha_(0.13, 1.0).CGColor())
            divider.setAutoresizingMask_(16 | 4)

        web_config = WKWebViewConfiguration.alloc().init()
        web_config.preferences().setJavaScriptCanOpenWindowsAutomatically_(True)
        web_config.setApplicationNameForUserAgent_(SAFARI_UA_SUFFIX)
        self._web = WKWebView.alloc().initWithFrame_configuration_(
            NSMakeRect(side, 0, max(200.0, w - side), h), web_config
        )
        self._web.setAutoresizingMask_(2 | 16)  # width and height sizable
        self._web.setNavigationDelegate_(self._bridge)
        self._web.setUIDelegate_(self._bridge)
        content.addSubview_(self._web)
        if sidebar_html:
            content.addSubview_(divider)
        self.navigate(start_url)
        win.makeFirstResponder_(self._web)

    # --- behaviour --------------------------------------------------------

    def _swallow_shortcuts(self, event):
        """Eat Cmd-Q / W / H / M / Tab / ` so the lock can't be dismissed."""
        if event.modifierFlags() & NS_CMD:
            key = (event.charactersIgnoringModifiers() or "").lower()
            if key in ("q", "w", "h", "m", "`", "\t"):
                return None
        return event

    def raise_to_front(self):
        if not self.visible:
            return
        NSApp().activateIgnoringOtherApps_(True)
        for win in self._windows:
            win.orderFrontRegardless()

    def on_message(self, data):
        self._on_message(data)

    def navigate(self, url):
        if self._web is None:
            return
        nsurl = NSURL.URLWithString_(url)
        if nsurl is not None:
            self._web.loadRequest_(NSURLRequest.requestWithURL_(nsurl))

    def sidebar_js(self, script):
        """Run JavaScript in the sidebar, e.g. to show an error without re-rendering it."""
        if self._sidebar is not None:
            self._sidebar.evaluateJavaScript_completionHandler_(script, None)

    def focus_sidebar(self):
        if self._windows and self._sidebar is not None:
            self._windows[0].makeFirstResponder_(self._sidebar)

    def focus_web(self):
        if self._windows and self._web is not None:
            self._windows[0].makeFirstResponder_(self._web)
