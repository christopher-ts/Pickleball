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

`scraper/scrape.py` loads the search page in a real headless browser (to
get session cookies right) and reads the site's own internal API response
directly: `POST .../rest/activities/list` returns structured JSON
(`body.activity_items`) with name, day/time, location, openings, and
enroll links — confirmed against real Santa Monica data. That's a private,
undocumented endpoint though, not a stable public API, so if Santa Monica
ever changes its shape, `data/debug_capture.json` (written on every run)
has the raw captured response to re-diagnose from, and `build_session_entry()`
in `scraper/scrape.py` is where the field-name assumptions live.

If the ActiveCommunities site ends up blocking automated requests from
GitHub Actions' IP ranges, run the same two scripts from your own machine
on a cron job (or `launchd` on macOS) instead — nothing about them is
GitHub-specific other than the workflow file.

## Deferred ideas

**Auto-add-to-cart.** Clicking "Enroll" on a card still lands on Santa
Monica's own participant-selection page before it reaches the cart — an
extra step. We looked at closing that gap and tabled it; considered
approaches, from safest to riskiest:

- **Browser userscript** (Tampermonkey/Greasemonkey) that runs only in your
  own already-logged-in browser tab and auto-selects the participant when
  you land on that page. No credentials touch the app or any server. This
  is the one worth building if we pick this back up.
- **Smarter deep link** — check whether the enroll URL accepts a parameter
  that pre-selects a participant and skips the screen entirely. Unproven;
  needs testing against the real page while logged in.
- **Fully automated server-side add-to-cart** — the app logs into your SM
  Rec account itself and adds to cart unattended. Rejected: it turns a
  read-only scraper into something that takes a real reservation action
  with no human in the loop, requires storing real login credentials as a
  GitHub secret (a bigger exposure surface — e.g. our own diagnostic
  capture step earlier logged full raw network responses to a file
  committed into the public repo, which is exactly the kind of place a
  session token could leak from by accident), and risks tripping
  ActiveNet's bot detection or violating its terms of service.

## Scope

Only "open play" / "drop-in" pickleball sessions are surfaced (matched by
name/description). Leagues and clinics are filtered out by design — edit
`OPEN_PLAY_PATTERN` in `scraper/scrape.py` if you want to widen that.
