# Coal Harbour hotel tracker

Checks Google Hotels prices for six Coal Harbour hotels (Nov 12-14, 2026, 2 guests), keeps a history,
shows it on a dashboard, and sends a phone alert on new lows. It also watches StayVancouverHotels.com and
alerts you when a new promotion code appears (for example a gift card offer).

## Files
- `config.json`  dates, hotels, optional `target_total` (alert when a 2-night total drops to or below it)
- `tracker.py`   fetches prices, saves history, sends alerts (Python standard library only)
- `.github/workflows/track.yml`  runs the script daily on GitHub for free
- `docs/index.html`  the dashboard (reads `docs/prices.json` and `docs/offers.json`)

## Setup (about 20 minutes)

1. **SerpApi key.** Sign up at serpapi.com and copy your API key. Check the free plan's monthly search limit:
   6 hotels once a day until Nov 12 is roughly 330 searches. If that's over your limit, delete some hotels
   from `config.json` or use a paid tier for a month.
2. **Phone alerts.** Install the free ntfy app (iOS/Android), tap "+", and subscribe to a hard-to-guess topic
   name like `jake-hotels-7f3k29x`. Anyone who knows the topic can read it, so make it random.
3. **GitHub repo.** Create a new repository (public is simplest, since free GitHub Pages needs public) and upload
   everything in this folder, including the hidden `.github` folder.
4. **Secrets.** Repo Settings > Secrets and variables > Actions > New repository secret:
   - `SERPAPI_KEY` = your SerpApi key
   - `NTFY_TOPIC` = the topic name from step 2
5. **First run.** Actions tab > "Track hotel prices" > Run workflow. Watch the log; each hotel prints a price.
6. **Dashboard.** Settings > Pages > Deploy from a branch > `main` and folder `/docs`. Your page will be at
   `https://YOUR-USERNAME.github.io/YOUR-REPO/`. Bookmark it on your phone.

Set a budget alert: put a number in `target_total` in `config.json` (for example `1100`).

## Notes and limits
- I couldn't run this against the live SerpApi from where I built it, so the first run is your test. If a hotel
  says "no property matching", open the log (it lists what Google returned) and adjust that hotel's `query` or
  `match` in `config.json`.
- Google totals are often before some taxes and fees. Compare hotels to each other, not to the final bill.
- Prices are Google's, mostly public rates. Member and direct rates can differ, and Stay Vancouver gift cards
  are never in these numbers.
- The offers watcher reads the public Offers page. If Stay Vancouver redesigns the page, it may stop finding codes.
- The job stops on its own after check-in day. When you've booked, delete the repo or disable the workflow.
- To test on your computer: `SERPAPI_KEY=xxxx NTFY_TOPIC=yyyy python tracker.py`
