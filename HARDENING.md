# Hardening: for the friend, not for you

Out of the box, kiosklock is friction. These steps make it a lock. **Your friend runs them with their own admin password on your Mac, while you're not watching.**

If you run them yourself, you can undo them yourself, and the whole thing is theatre.

---

## Step 1: Make the agent impossible to remove

This makes the LaunchAgent root-owned and flags it system-immutable, so it can't be edited or deleted without booting into Recovery.

Run `python3 -m kiosklock install` first, then:

```bash
PLIST="$HOME/Library/LaunchAgents/com.kiosklock.agent.plist"
sudo chown root:wheel "$PLIST"
sudo chmod 644 "$PLIST"
sudo chflags schg "$PLIST"
```

Do the same for the code and the password, so neither can be swapped out:

```bash
sudo chown -R root:wheel /path/to/kiosk-lock-mac
sudo chflags -R schg /path/to/kiosk-lock-mac
sudo chflags schg "$HOME/.kiosklock/config.json"
```

Leave the `~/.kiosklock` folder itself writable: that's where the current lock (`lock.json`) is saved and cleared. Only `config.json`, which holds the password hash, gets frozen.

To undo, from Recovery or with the admin password:

```bash
sudo chflags -R noschg /path/to/kiosk-lock-mac "$HOME/.kiosklock/config.json" "$PLIST"
sudo rm -f "$PLIST"
```

## Step 2: Take away admin

Step 1 is pointless if the account can `sudo`. In **System Settings → Users & Groups**, your friend should:

1. Create their own admin account with a password only they know.
2. Change your account to **Standard**.

Now you can't `sudo`, can't unload a root-owned agent, and can't boot into Safe Mode to turn off login items without an admin password.

## Step 3 (optional): Firmware password

This blocks booting into Recovery or from an external drive, which is the last way around it. On Apple Silicon your friend sets it from Recovery under **Utilities → Startup Security Utility**.

Only do this if you're both certain. A forgotten firmware password on Apple Silicon means a trip to the Apple Store.

---

## What is deliberately not blocked

- **Powering off.** Always available. No exceptions.
- **The Mac's own emergency features.** Nothing here touches SOS, calls or Recovery.
- **The friend's password.** They can always end a lock early.

If your friend becomes unreachable and you're genuinely stuck, Step 1 can be undone from Recovery by anyone with the admin password from Step 2. That's why Step 3 is the one to think twice about.
