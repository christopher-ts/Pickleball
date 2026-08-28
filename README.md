# SM Pickleball

A tiny personal app that watches Santa Monica Rec's ActiveCommunities site
for open-play pickleball sessions, so you don't have to click through the
official search UI to check.

- **`docs/`** — a static page (hosted on GitHub Pages) listing current
  sessions, filterable by day/location, linking straight to registration.
- **`scraper/`** — a Playwright script that scrapes the search results and a
  notifier that pushes a [ntfy.sh](https://ntfy.sh) alert when a new session
  appears or one flips from full/not-yet-open to open.
- **`.github/workflows/poll.yml`** — runs the scraper on a schedule (every
  20 minutes) and commits the refreshed data.

## One-time setup

1. **Pick an ntfy topic** — a private, hard-to-guess string (ntfy topics are
   public-by-name, so don't use something guessable like `pickleball`).
   Install the [ntfy app](https://ntfy.sh/#subscribe) on your phone and
   subscribe to that topic.
2. **Add the secret** — in this repo, go to Settings → Secrets and
   variables → Actions → New repository secret, name it `NTFY_TOPIC`, and
   paste your topic string.
3. **Enable GitHub Pages** — Settings → Pages → Source: "Deploy from a
   branch" → Branch: `main`, folder `/docs`. The page will be live at
   `https://<you>.github.io/<repo>/` a minute or two later, and refreshes
   automatically whenever the scraper commits new data.
4. **Merge this branch to `main`** (or point Pages at this branch instead)
   so the scheduled workflow and Pages site are live from the branch you
   actually keep around.

## Running it yourself

```bash
pip install -r scraper/requirements.txt
playwright install --with-deps chromium
python scraper/scrape.py   # writes data/sessions.json + data/debug_capture.json
python scraper/notify.py   # needs NTFY_TOPIC in the environment
```

## Notes / current status

This was built without the ability to load the real ActiveCommunities site
from the dev environment, so `scraper/scrape.py` currently parses whatever
JSON API responses it captures from the rendered page in a generic,
best-effort way (see `data/debug_capture.json` after a run). If Santa
Monica's site structure differs from what it guesses, the session list in
`data/sessions.json` may come back thin or empty — check
`debug_capture.json` for the raw captured network responses and adjust the
field-name guesses in `scraper/scrape.py`'s `build_session_entry()`
accordingly.

If the ActiveCommunities site ends up blocking automated requests from
GitHub Actions' IP ranges, run the same two scripts from your own machine
on a cron job (or `launchd` on macOS) instead — nothing about them is
GitHub-specific other than the workflow file.

## Scope

Only "open play" / "drop-in" pickleball sessions are surfaced (matched by
name/description). Leagues and clinics are filtered out by design — edit
`OPEN_PLAY_PATTERN` in `scraper/scrape.py` if you want to widen that.
