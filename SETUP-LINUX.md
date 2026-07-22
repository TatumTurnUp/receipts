# Running Receipts on Linux — from zero to running

No coding needed. Takes about 10 minutes.

## Step 1 — Make sure you have Python

Open a terminal and run:

```
python3 --version
```

Most distros ship Python already. If yours doesn't, or if you're on
Debian/Ubuntu/Mint, also make sure the venv module is present:

```
sudo apt install python3 python3-venv python3-pip     # Debian/Ubuntu/Mint
sudo dnf install python3                              # Fedora
sudo pacman -S python                                 # Arch
```

## Step 2 — Download Receipts

Either grab the ZIP: GitHub page → green **`< > Code`** button →
**Download ZIP** → extract it somewhere permanent (e.g. `~/Documents/Receipts`).

Or clone it:

```
git clone <the-repo-url> ~/Documents/Receipts
```

## Step 3 — First launch

```
cd ~/Documents/Receipts        # or wherever you put it
bash start.sh
```

First run takes a minute while it creates a virtual environment and installs
dependencies. Then your browser opens to the app automatically
(it lives at `http://localhost:8765`).

The terminal stays open while the app runs. Running `start.sh` again when it's
already running just reopens the browser.

**Recommended — install it as a real app:**

```
bash install-launcher.sh
```

This adds 🧾 **Receipts** to your app menu with its own icon (log out/in if it
doesn't show up immediately). Click it like any app — it starts the server and
opens the browser. Pin it to your panel/dock. If you ever move the folder,
run the installer again.

Everything you upload stays on your computer, in a `receipts-data` folder that
appears next to the app. Nothing is uploaded to any server or cloud (only items
being analyzed are sent to the AI, and only if you finish Step 4).

## Step 4 — Turn on the AI (optional but it's the magic)

The app works without this (uploads, folders, timelines, keyword search), but
AI analysis and question-answering need an Anthropic API key.

**Heads up:** this is separate from a Claude Pro subscription. Pro covers the
claude.ai app; the API is its own account with pay-as-you-go billing. At
personal usage (analyzing screenshots, occasional searches) costs are typically
cents-to-a-few-dollars a month, and you can set a hard spending limit.

1. Go to **https://console.anthropic.com** and sign in (you can use the same
   email as your Claude account).
2. Add billing: **Settings → Billing** — add a payment method and buy a small
   amount of credit ($5 is plenty to start). You can set a monthly spend limit
   on the same page.
3. Create a key: **Settings → API Keys → Create Key**. Name it "Receipts".
   Copy the key immediately — it's shown only once. It looks like `sk-ant-...`
4. In Receipts, click **Settings & AI** (bottom-left corner) → paste the key →
   pick a model (Sonnet is the sensible default; Opus is smarter and pricier;
   Haiku is cheapest) → **Save**. The dot next to Settings turns green.

Treat the key like a password: don't share it, don't post it anywhere.

## Quick start using it

1. **➕ New module** → pick a type (Person, Event, Place, Project) → name it,
   and write good Notes — the AI reads them to understand what it's looking at.
2. Open the module → **⬆ Upload files** → drop in screenshots. Add a context
   note ("texts with Sarah from around March") — it dramatically improves the
   AI's dating and summaries. Set a manual date only if you know it.
3. Every record gets a timestamp with a colored 1–10 confidence chip
   (green = stated in the content, red = metadata guess). Click any record to
   see the reasoning, fix the date, or view its full audit trail.
4. Search from Home in plain English: *"Have Sarah and I ever talked about
   that taco place?"*

## If something goes wrong

- **`ensurepip is not available`** during first run → install the venv package
  (see Step 1) then delete the `.venv` folder and run `start.sh` again.
- **Browser doesn't open** → go to `http://localhost:8765` manually.
- **Nothing happens clicking the menu icon** → run `bash start.sh` in a
  terminal once to see the error.
- **AI errors on upload** → files still save; open the record and hit
  **Re-analyze**. Usually it's a missing/expired key or no API credit.
