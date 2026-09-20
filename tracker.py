#!/usr/bin/env python3
"""Coal Harbour hotel price tracker.

Fetches Google Hotels prices through SerpApi for the hotels in config.json,
appends them to docs/prices.json, sends a phone alert (ntfy) on new lows,
and watches StayVancouverHotels.com for newly listed promotions.

Environment variables:
  SERPAPI_KEY  required  your SerpApi key
  NTFY_TOPIC   optional  ntfy.sh topic name for phone alerts
Standard library only, no pip install needed.
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CFG = json.loads((ROOT / "config.json").read_text())
PRICES = ROOT / "docs" / "prices.json"
OFFERS = ROOT / "docs" / "offers.json"
KEY = os.environ.get("SERPAPI_KEY", "")
NTFY = os.environ.get("NTFY_TOPIC", "")
UA = {"User-Agent": "Mozilla/5.0 (personal hotel price tracker)"}

CHECKIN = date.fromisoformat(CFG["checkin"])
CHECKOUT = date.fromisoformat(CFG["checkout"])
NIGHTS = (CHECKOUT - CHECKIN).days


def get(url, timeout=60):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def notify(title, body, click=None, priority="default"):
    print(f"[alert] {title}: {body}")
    if not NTFY:
        return
    headers = {
        "Title": title.encode("ascii", "ignore").decode(),
        "Priority": priority,
        "Tags": "hotel",
    }
    if click:
        headers["Click"] = click
    req = urllib.request.Request(
        "https://ntfy.sh/" + NTFY, data=body.encode("utf-8"), headers=headers, method="POST"
    )
    try:
        urllib.request.urlopen(req, timeout=30)
    except Exception as e:  # alerts must never crash the run
        print("ntfy failed:", e)


def search(query):
    params = {
        "engine": "google_hotels",
        "q": query,
        "check_in_date": CFG["checkin"],
        "check_out_date": CFG["checkout"],
        "adults": CFG.get("adults", 2),
        "currency": CFG.get("currency", "CAD"),
        "gl": CFG.get("gl", "ca"),
        "hl": "en",
        "api_key": KEY,
    }
    return json.loads(get("https://serpapi.com/search.json?" + urllib.parse.urlencode(params)))


def lowest(d):
    return d.get("extracted_lowest") if isinstance(d, dict) else None


def pick(result, hotel):
    """Return (name, nightly, total, source, official). `official` is (total, source) from the hotel's own site when found, else None."""
    if result.get("error"):
        raise RuntimeError(result["error"])
    match = hotel["match"].lower()

    props = result.get("properties")
    if props:
        found = next((p for p in props if match in p.get("name", "").lower()), None)
        if not found:
            names = ", ".join(p.get("name", "?") for p in props[:6])
            raise RuntimeError(f"no property matching '{match}' (got: {names})")
        nightly, total = lowest(found.get("rate_per_night")), lowest(found.get("total_rate"))
        if total is None and nightly is not None:
            total = nightly * NIGHTS
        if nightly is None and total is not None:
            nightly = total / NIGHTS
        if total is None:
            raise RuntimeError("property has no price (sold out for these dates?)")
        return found["name"], nightly, total, "Google Hotels", None

    # Single-property result: several booking sites each with a price.
    rows = []
    official = None
    for o in (result.get("featured_prices") or []) + (result.get("prices") or []):
        n, t = lowest(o.get("rate_per_night")), lowest(o.get("total_rate"))
        if t is None and n is not None:
            t = n * NIGHTS
        if n is None and t is not None:
            n = t / NIGHTS
        if t:
            rows.append((t, n, o.get("source", "")))
            src = (o.get("source") or "").lower()
            is_official = o.get("official") or any(k in src for k in hotel.get("official_match", []))
            if is_official and (official is None or t < official[0]):
                official = (t, o.get("source", ""))
    if not rows:
        raise RuntimeError("no prices in response (sold out for these dates?)")
    t, n, s = min(rows)
    return result.get("name", hotel["name"]), n, t, s, official


def check_offers(now):
    """Alert when StayVancouverHotels lists a promo code we haven't seen before."""
    try:
        html = get("https://www.stayvancouverhotels.com/exclusive-offers.php")
    except Exception as e:
        print("offers page failed:", e)
        return
    codes = sorted(set(re.findall(r"stayvancouverhotels/([A-Za-z0-9_]+)", html)))
    if not codes:
        print("offers page: no promo codes found, leaving saved list alone")
        return
    seen = None
    if OFFERS.exists():
        seen = json.loads(OFFERS.read_text()).get("codes", [])
    if seen is not None:
        new = [c for c in codes if c not in seen]
        if new:
            hot = any(re.search(r"prepaid|gift|card|cash", c, re.I) for c in new)
            notify(
                "New Stay Vancouver offer" + ("s" if len(new) > 1 else ""),
                "New promo code(s): " + ", ".join(new),
                click="https://www.stayvancouverhotels.com/exclusive-offers.php",
                priority="high" if hot else "default",
            )
    OFFERS.write_text(json.dumps({"updated": now, "codes": codes}, indent=1))


def main():
    if not KEY:
        sys.exit("Set the SERPAPI_KEY environment variable.")
    if date.today() > CHECKIN:
        print("Check-in date has passed; nothing to track.")
        return

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    data = json.loads(PRICES.read_text()) if PRICES.exists() else {}
    hist = data.setdefault("history", [])
    data.update(
        checkin=CFG["checkin"],
        checkout=CFG["checkout"],
        currency=CFG.get("currency", "CAD"),
        target_total=CFG.get("target_total"),
        hotels=[
            {"id": h["id"], "name": h["name"], "sv": h.get("sv", ""), "member": h.get("member")}
            for h in CFG["hotels"]
        ],
    )
    target = CFG.get("target_total")
    got = 0

    for h in CFG["hotels"]:
        try:
            name, nightly, total, source, official = pick(search(h["query"]), h)
        except Exception as e:
            print(f"{h['name']}: skipped ({e})")
            continue
        got += 1
        prev = [x["total"] for x in hist if x["hotel"] == h["id"] and x.get("total")]
        entry = {"t": now, "hotel": h["id"], "total": round(total), "nightly": round(nightly), "source": source}
        if official:
            entry["official"] = round(official[0])
            entry["official_src"] = official[1]
        hist.append(entry)
        print(f"{h['name']}: ${total:,.0f} total, ${nightly:,.0f}/night via {source}")
        if h.get("member"):
            print(f"  hotel's own rate: {'$%s via %s' % (format(official[0], ',.0f'), official[1]) if official else 'not found in results'}")

        link = "https://www.google.com/travel/search?q=" + urllib.parse.quote(
            f"{h['name']} Vancouver {CFG['checkin']} to {CFG['checkout']}"
        )
        if prev and total < min(prev):
            notify(
                f"New low: {h['name']}",
                f"${total:,.0f} for {NIGHTS} nights (was ${min(prev):,.0f}) via {source}",
                click=link,
                priority="high",
            )
        elif target and total <= target and (not prev or min(prev) > target):
            notify(f"Under target: {h['name']}", f"${total:,.0f} for {NIGHTS} nights via {source}", click=link)

    if got == 0:
        sys.exit("No prices retrieved for any hotel. Check the log above and your SerpApi key/quota.")

    data["updated"] = now
    PRICES.write_text(json.dumps(data, indent=1))
    check_offers(now)


if __name__ == "__main__":
    main()
