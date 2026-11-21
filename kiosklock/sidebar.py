"""The sidebar shown inside the lock: what this is, time left, and the friend unlock."""

import html
import json

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: #0b0d12; color: #e8ecf3; height: 100vh; overflow-y: auto;
  font: 13px/1.5 -apple-system, "SF Pro Text", system-ui, sans-serif;
  padding: 28px 24px 32px; -webkit-user-select: none; cursor: default;
}
.brand { font-size: 11px; letter-spacing: .22em; color: #5b6577; text-transform: uppercase; }
h1 { font-size: 22px; font-weight: 680; letter-spacing: -.02em; margin: 8px 0 4px; line-height: 1.25; }
.left { font-size: 44px; font-weight: 700; letter-spacing: -.03em; margin: 22px 0 0;
        font-variant-numeric: tabular-nums; }
.until { color: #8b95a8; font-size: 12.5px; }
.bar { height: 4px; background: #1c212c; border-radius: 2px; margin: 14px 0 26px; overflow: hidden; }
.bar i { display: block; height: 100%; background: #4c8dff; width: 0; transition: width 1s linear; }
h2 { font-size: 10.5px; letter-spacing: .18em; color: #5b6577; text-transform: uppercase; margin: 0 0 10px; }
ul { list-style: none; margin-bottom: 26px; }
li { padding: 7px 0; border-bottom: 1px solid #151a23; }
li:last-child { border-bottom: 0; }
a { color: #9db9ff; text-decoration: none; cursor: pointer; }
a:hover { text-decoration: underline; }
button { font: inherit; font-weight: 560; border: 1px solid #232a36; background: #151a23;
         color: #e8ecf3; border-radius: 9px; padding: 10px; cursor: pointer; width: 100%; }
button:hover { background: #1b212c; }
button.quiet { background: transparent; border-color: #2a1e22; color: #8a6b73; font-weight: 400; font-size: 12px; }
button.quiet:hover { background: #1a1216; color: #d08a97; }
.prompt { background: #11151d; border: 1px solid #232a36; border-radius: 11px; padding: 16px; display: none; }
.prompt.open { display: block; }
.prompt p { color: #8b95a8; font-size: 12px; margin-bottom: 12px; }
.prompt input { width: 100%; font: inherit; padding: 9px 11px; border-radius: 8px; border: 1px solid #2b3444;
                background: #0b0d12; color: #e8ecf3; margin-bottom: 10px; -webkit-user-select: text; }
.prompt input:focus { outline: none; border-color: #4c8dff; }
.prompt .row { display: flex; gap: 8px; }
.err { color: #ff8a8a; font-size: 12px; margin-bottom: 10px; display: none; }
.note { color: #4e5766; font-size: 11px; margin-top: 18px; line-height: 1.5; }
.test { background: #2a1f12; border: 1px solid #4a3620; color: #ffc46b; border-radius: 9px;
        padding: 10px 12px; margin-bottom: 18px; font-size: 12px; }
"""

SCRIPT = """
const until = %(until)s * 1000, started = %(started)s * 1000;
const post = (m) => window.webkit.messageHandlers.kiosklock.postMessage(m);
function fmt(ms) {
  const s = Math.max(0, Math.ceil(ms / 1000)), h = Math.floor(s / 3600), m = Math.floor(s %% 3600 / 60), r = s %% 60;
  return (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(r).padStart(2, '0');
}
function tick() {
  const now = Date.now();
  document.getElementById('left').textContent = fmt(until - now);
  document.getElementById('fill').style.width = Math.min(100, (now - started) / (until - started) * 100) + '%%';
}
tick(); setInterval(tick, 1000);
document.getElementById('until').textContent =
  'until ' + new Date(until).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
document.querySelectorAll('[data-url]').forEach((a) => a.onclick = () => post({ action: 'open', url: a.dataset.url }));
const prompt = document.getElementById('prompt'), pw = document.getElementById('pw'), err = document.getElementById('err');
document.getElementById('ask').onclick = () => { prompt.classList.add('open'); post({ action: 'prompt' }); setTimeout(() => pw.focus(), 50); };
document.getElementById('cancel').onclick = () => { prompt.classList.remove('open'); err.style.display = 'none'; pw.value = ''; post({ action: 'cancel' }); };
function submit() { post({ action: 'unlock', password: pw.value }); pw.value = ''; }
document.getElementById('go').onclick = submit;
pw.addEventListener('keydown', (e) => { if (e.key === 'Enter') submit(); });
window.showError = (text) => { err.textContent = text; err.style.display = 'block'; pw.focus(); };
"""


def render(lock, test_seconds=None):
    hosts = lock["allowed_hosts"]
    links = "".join(
        '<li><a data-url="https://%s/">%s</a></li>' % (html.escape(h), html.escape(h)) for h in hosts
    )
    test = (
        '<div class="test">Test mode: releases itself after %d seconds.</div>' % test_seconds
        if test_seconds else ""
    )
    return """<!doctype html><html><head><meta charset="utf-8"><style>%(css)s</style></head><body>
%(test)s
<div class="brand">Locked</div>
<h1>%(message)s</h1>
<div class="left" id="left"></div>
<div class="until" id="until"></div>
<div class="bar"><i id="fill"></i></div>
<h2>You can use</h2>
<ul>%(links)s</ul>
<button class="quiet" id="ask">Friend unlock</button>
<div class="prompt" id="prompt">
  <p>Hand the laptop to the person who set the password.</p>
  <div class="err" id="err">That isn't the password.</div>
  <input id="pw" type="password" placeholder="Password" autocomplete="off">
  <div class="row"><button id="cancel">Cancel</button><button id="go">Unlock</button></div>
</div>
<p class="note">%(note)s</p>
<script>%(script)s</script>
</body></html>""" % {
        "css": CSS,
        "test": test,
        "message": html.escape(lock.get("message") or "Focus time"),
        "links": links,
        "note": ("Nothing is saved in test mode." if test_seconds else
                 "Powering off always works. The lock comes back at login until the time is up."),
        "script": SCRIPT % {"until": json.dumps(lock["until"]), "started": json.dumps(lock["started"])},
    }
