# Running Receipts on Mac — from zero to running

No coding needed. Takes about 10 minutes.

## Step 1 — Make sure you have Python

1. Open **Terminal** (press Cmd+Space, type "Terminal", hit Enter).
2. Type `python3 --version` and press Enter.
   - If you see something like `Python 3.12.x` → you're set, go to Step 2.
   - If it offers to install "command line developer tools" → click **Install**,
     wait for it to finish, then you're set.
   - If it says "command not found" → download Python from
     **https://python.org/downloads** and run the installer.

## Step 2 — Download Receipts

1. Open the GitHub link you were sent.
2. Click the green **`< > Code`** button → **Download ZIP**.
3. Double-click the ZIP in Downloads to extract it.
4. Move the extracted folder somewhere permanent, like your **Documents** folder.

## Step 3 — First launch

1. Open Terminal, type `cd ` (with a space after it), then **drag the receipts
   folder from Finder into the Terminal window** — it fills in the path for you.
   Press Enter.
2. Type `bash start.sh` and press Enter.
3. First run takes a minute while it sets itself up. Then your browser opens
   to the app automatically (it lives at `http://localhost:8765`).
4. Leave the Terminal window open while you use the app — that IS the app.
   To use Receipts later: same two commands (`cd` + drag, `bash start.sh`).
   If the app is already running, running it again just reopens the browser.

**Optional — one-click launching:** in Finder, right-click `start.sh` →
Get Info → Open with → Terminal → "Change All". Or make an alias: drag
`start.sh` to your Dock's right side. macOS may warn the first time you open
it ("from an unidentified developer") — right-click → **Open** → Open.

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

- **"permission denied"** when running start.sh → run `chmod +x start.sh` once,
  then try again.
- **Browser doesn't open** → go to `http://localhost:8765` manually.
- **AI errors on upload** → files still save; open the record and hit
  **Re-analyze**. Usually it's a missing/expired key or no API credit.
