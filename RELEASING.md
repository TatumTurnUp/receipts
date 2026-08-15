# How to work on Receipts and release it

Written for one person maintaining this. No prior knowledge assumed.

---

## The two branches

- **`dev`** — where you work. Every Claude Code session, every edit, every experiment.
- **`main`** — only ever holds code that has been released.

That's the whole branching model. You do not need anything more complicated.

```bash
git checkout dev          # start working
# ...make changes...
git add -A && git commit -m "what you changed"
git push
```

---

## Working day to day

Run from source, exactly like you do now:

```bash
python launch.py
```

**One thing to set up once**, so you can never damage your real archive while
developing:

```bash
export RECEIPTS_DATA=~/receipts-dev-archive
```

Put that line in your `~/.zshrc` (Mac) or `~/.bashrc` (Linux) and forget about
it. With it set, running from source uses a scratch archive. Your real one is
untouched no matter what you break. That single environment variable is your
"separate development environment" — there is nothing else to configure.

Before you commit anything, run the tests:

```bash
pytest tests/
```

If they're green, an update cannot eat anyone's data. If they're red, stop and
fix it — that suite is the only thing standing between a bad edit and someone's
irreplaceable archive.

---

## Releasing a beta to your 3 friends

When you have something you want tested but not everyone to get:

```bash
git checkout dev
git tag v1.1.0-beta.1
git push --tags
```

Wait about fifteen minutes. GitHub builds Mac, Windows and Linux versions and
puts them on your Releases page marked **Pre-release**. Send your three friends
the link. Nobody else sees it unless you send it to them.

Found a problem? Fix it, then `v1.1.0-beta.2`, and so on.

---

## Releasing to everyone

Once the beta looks good:

```bash
git checkout main
git merge dev
git tag v1.1.0
git push origin main --tags
```

Same fifteen minutes, same three platforms, published as the current release.

---

## Version numbers

`MAJOR.MINOR.PATCH` — for your purposes:

- Fixed a bug: `1.1.0` → `1.1.1`
- Added a feature: `1.1.1` → `1.2.0`
- Changed something fundamental: `1.2.0` → `2.0.0`

You do not edit `version.py` by hand. The tag is the source of truth; the build
stamps it in.

---

## The rule that protects everyone's data

**Never change an existing database column or delete one.** Only ever add.

When you need a new field, add it to the `MIGRATIONS` dict in `app.py` and bump
`SCHEMA_VERSION`:

```python
SCHEMA_VERSION = 9

MIGRATIONS = {
    ...
    9: ["ALTER TABLE modules ADD COLUMN brings_joy INTEGER NOT NULL DEFAULT 0"],
}
```

Then add a fixture for the shape you're leaving behind in
`tests/legacy_schemas.py`, and run the tests. That's the ritual. Follow it and
updates stay safe forever.

`CLAUDE.md` states this as a binding rule for any AI session that touches the
project, so Claude Code will follow it too — but check the diff anyway.

---

## What happens to someone's data when they update

Nothing. That's the design, and it's worth knowing why so you don't
accidentally undo it:

1. Their archive lives in a per-user OS folder, **outside** the app. The
   installer replaces the app; it cannot reach the archive.
2. Before any database format change, a permanent backup is taken and never
   deleted.
3. Migrations run in a transaction — if one fails, everything rolls back.
4. The app refuses to open an archive from a *newer* version rather than write
   into a shape it doesn't understand. This is what makes the beta channel
   safe: a tester who goes back to stable gets a clear message, not corruption.
5. Settings → **Export everything** gives them a zip of the whole archive at any
   time.

If you ever find yourself writing a file path relative to the app folder for
something the user owns, stop. That's the one mistake that would break all of
this.

---

## Costs

- **Apple Developer Program — $99/year.** Without it, Mac users get "Apple
  cannot check it for malicious software" and have to right-click → Open.
- **Windows — nothing, for now.** Certificates no longer skip the SmartScreen
  warning; reputation is earned through download volume. At ten users you'd be
  paying for nothing. Revisit around a hundred.
- **Everything else — free.** GitHub builds and hosts the downloads.

### Setting up Apple signing

Enrolment takes a few days, so start it early. Once you're in, add these to
**Settings → Secrets and variables → Actions** on the GitHub repo:

| Secret | What it is |
|---|---|
| `MACOS_CERT_P12` | Your Developer ID certificate, exported as .p12, base64-encoded |
| `MACOS_CERT_PASSWORD` | The password you set when exporting it |
| `MACOS_SIGN_IDENTITY` | e.g. `Developer ID Application: Your Name (TEAMID)` |
| `APPLE_ID` | Your Apple ID email |
| `APPLE_TEAM_ID` | Ten characters, from your developer account |
| `APPLE_APP_PASSWORD` | An app-specific password from appleid.apple.com |

The build signs and notarizes automatically once those exist. Until then it
still produces working downloads — they just show the warning.

---

## If a build fails

Go to the **Actions** tab on GitHub and click the red run. The failing step is
expanded. Common causes:

- **Tests failed** — the release was stopped on purpose. Fix and re-tag.
- **A tag already exists** — delete it (`git tag -d v1.1.0` and
  `git push --delete origin v1.1.0`) and tag again.
- **Notarization timed out** — Apple was slow. Re-run the job; nothing is lost.
