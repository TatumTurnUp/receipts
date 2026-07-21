# Running Receipts on Windows — from zero to running

No coding needed. Takes about 10 minutes.

## Step 1 — Install Python

1. Go to **https://python.org/downloads** and click the big yellow **Download Python** button.
2. Run the installer. **IMPORTANT:** on the first screen, check the box that says
   **"Add python.exe to PATH"** (bottom of the window) before clicking Install.
   If you miss this, nothing else will work — rerun the installer and choose it.

## Step 2 — Download Receipts

1. Open the GitHub link you were sent.
2. Click the green **`< > Code`** button → **Download ZIP**.
3. Find the ZIP in your Downloads, right-click → **Extract All**.
4. Move the extracted folder somewhere permanent, like `Documents\Receipts`.
   (Don't run it from inside the ZIP or from Downloads.)

## Step 3 — First launch

1. Open the folder and double-click **`start.bat`**.
2. A black window appears and says it's setting things up — this takes a minute
   the first time. If Windows shows a SmartScreen warning, click
   **More info → Run anyway** (it's a plain script; you can open it in Notepad
   to see everything it does).
3. When it's ready, your browser opens to the app automatically
   (it lives at `http://localhost:8765`).
4. Leave the black window open while you use the app — that IS the app.
   Closing it shuts Receipts down. To use Receipts later, just double-click
   `start.bat` again.

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

- **"Python is not recognized"** → Python isn't on PATH. Rerun the installer,
  check the PATH box.
- **The black window flashes and vanishes** → right-click `start.bat` →
  Edit to make sure it's intact, or open Command Prompt in the folder and run
  `start.bat` to see the error message.
- **Browser doesn't open** → go to `http://localhost:8765` manually.
- **AI errors on upload** → files still save; open the record and hit
  **Re-analyze**. Usually it's a missing/expired key or no API credit.
