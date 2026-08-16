# Installing Receipts

Download page: **https://github.com/TatumTurnUp/receipts/releases**

Grab the file for your computer, then follow the short section below for it.

| Your computer | Download the file ending in |
|---|---|
| Mac with Apple Silicon (M1, M2, M3, M4) | `-macos-arm64.dmg` |
| Mac with an Intel chip | `-macos-intel.dmg` |
| Windows | `Receipts-Setup-….exe` |
| Linux | `-x86_64.AppImage` |

Not sure which Mac you have? Click the  menu → **About This Mac**. If the
chip line says "Apple", you want `arm64`.

---

## Mac

1. Open the `.dmg` you downloaded.
2. Drag **Receipts** into your **Applications** folder.
3. Open it from Applications.

**The first time, macOS will refuse to open it** and say Receipts "cannot be
opened because it is from an unidentified developer," or that Apple cannot
check it for malicious software.

That message is about a certificate, not about the app. Receipts isn't signed
with an Apple developer certificate yet, so macOS won't vouch for it. To open
it anyway:

1. Go to  → **System Settings** → **Privacy & Security**
2. Scroll down to the **Security** section — you'll see a line about Receipts
   being blocked
3. Click **Open Anyway**
4. Confirm, and enter your password if asked

You only do this once. Every launch after that is a normal double-click.

> If you've done this on older Macs before: right-clicking and choosing "Open"
> used to work. Apple removed that shortcut in macOS Sequoia, so the System
> Settings route above is now the only way.

---

## Windows

1. Run the `Receipts-Setup-….exe` you downloaded.
2. Windows will show a blue box: **"Windows protected your PC."**
3. Click **More info**, then **Run anyway**.
4. Follow the installer. It doesn't need an administrator password.

Same story as the Mac warning: the app isn't signed with a certificate, so
Windows doesn't recognise the publisher. The warning fades as more people
download it.

If the installer offers to install a Microsoft component, let it — that's the
piece Windows uses to draw the app's window.

---

## Linux

1. Download the `.AppImage`.
2. Make it runnable, either by right-clicking → **Properties** → **Permissions**
   → tick *Allow executing file as program*, or in a terminal:
   ```bash
   chmod +x Receipts-*.AppImage
   ```
3. Double-click it, or run `./Receipts-*.AppImage`.

No installer, no root, nothing scattered across your system — it's one file.

---

## Where your stuff is kept

Everything you put into Receipts stays on your computer. Nothing is uploaded
anywhere.

| Your computer | Your archive lives in |
|---|---|
| Mac | `~/Library/Application Support/Receipts` |
| Windows | `%LOCALAPPDATA%\Receipts` |
| Linux | `~/.local/share/receipts` |

Settings shows you the exact path, and has an **Export everything** button that
hands you the whole archive — database and original files — as a single zip,
any time you want it.

That folder sits **outside** the app on purpose. Updating Receipts replaces the
app and never touches your archive. A permanent backup is taken before any
change to the archive's format, and if an update can't finish cleanly it rolls
back and leaves everything as it was.

Uninstalling doesn't delete your archive either. If you genuinely want it gone,
delete that folder yourself.

---

## Turning on the AI features (optional)

Receipts works without any AI: you can add records, organise them, search by
keyword, and browse the timeline.

The AI adds two things — reading uploaded screenshots to work out when they
were actually from, and answering questions in plain language. To switch it on,
open **Settings & AI** and paste in an Anthropic API key from
[console.anthropic.com](https://console.anthropic.com). Personal use runs well
under a dollar a month.

Your key is stored on your own machine and is never included in an export.

---

## Something went wrong?

Open an issue at
https://github.com/TatumTurnUp/receipts/issues and say what you did and what
happened. If the app won't start at all, there's a `startup-error.log` file in
the archive folder listed above — the contents of that will say why.

This is an early release. That's what the 0.9 means.
