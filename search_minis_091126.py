"""
AutoTrader MINI Cooper Convertible search tool.

Searches for used 2022-2025 MINI Cooper Convertibles with automatic
transmission, under $30,000, under 40,000 miles, within 500 miles of 95008.
Prints a table to the terminal and saves a timestamped CSV.
"""

import csv
import json
import sys
import time
from datetime import datetime
from urllib.parse import urlencode

from bs4 import BeautifulSoup
from curl_cffi import requests  # impersonates Chrome TLS to bypass bot checks
from tabulate import tabulate

# ── Search parameters ──────────────────────────────────────────────────────────
SEARCH = {
    "makeCode": "MINI",
    "vehicleStyleCode": "CONVERTIBLE",
    "startYear": 2019,
    "endYear": 2025,
    "transmissionCode": "AUT",  # AutoTrader's code for Automatic (not "A")
    "maxPrice": 31000,
    "mileage": 60000,           # AutoTrader param name is "mileage", not "maxMileage"
    "zip": "95008",
    "searchRadius": 500,
    "listingTypes": "USED",
    "sortBy": "distanceASC",
    "numRecords": 25,           # AutoTrader max per page
}

# Post-fetch filter: only keep trim names that indicate a Cooper S
REQUIRE_S_TRIM = True

BASE_URL = "https://www.autotrader.com"
SEARCH_URL = f"{BASE_URL}/cars-for-sale/used-cars"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}


def build_url(offset: int) -> str:
    params = {**SEARCH, "firstRecord": offset}
    return f"{SEARCH_URL}?{urlencode(params)}"


def is_cooper_s(item: dict) -> bool:
    """Return True if the listing trim indicates a Cooper S (not base, JCW, or SE)."""
    trim_raw = item.get("trim", {})
    trim = trim_raw.get("name", "") if isinstance(trim_raw, dict) else str(trim_raw)
    model_raw = item.get("model", {})
    model = model_raw.get("name", "") if isinstance(model_raw, dict) else str(model_raw)
    # Only the base "Cooper" (exact match) — excludes Countryman, Clubman, Paceman, etc.
    return model.strip() == "Cooper" and trim.strip() == "S"


def fetch(url: str, session: requests.Session) -> requests.Response | None:
    try:
        resp = session.get(url, headers=HEADERS, timeout=20, impersonate="chrome124")
        resp.raise_for_status()
        return resp
    except requests.exceptions.ConnectionError:
        print("ERROR: Could not connect to AutoTrader. Check your internet connection.")
    except requests.exceptions.Timeout:
        print("ERROR: Request timed out.")
    except requests.exceptions.HTTPError as exc:
        code = exc.response.status_code
        msgs = {
            403: "ERROR: AutoTrader blocked the request (HTTP 403). Try again in a few minutes.",
            429: "ERROR: Rate-limited by AutoTrader (HTTP 429). Wait and try again.",
        }
        print(msgs.get(code, f"ERROR: HTTP {code} from AutoTrader."))
    return None


def parse_page(html: str) -> tuple[list[dict], int]:
    """
    Returns (listings_on_this_page, total_result_count).
    Pulls data from the __NEXT_DATA__ JSON blob AutoTrader embeds in every page.
    """
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("script", {"id": "__NEXT_DATA__"})
    if not tag or not tag.string:
        return [], 0

    try:
        data = json.loads(tag.string)
    except json.JSONDecodeError:
        return [], 0

    try:
        eggs = data["props"]["pageProps"]["__eggsState"]
    except (KeyError, TypeError):
        return [], 0

    inventory: dict = eggs.get("inventory", {})
    owners: dict = eggs.get("owners", {})
    srp_results: dict = eggs.get("srp_results", {})
    total: int = srp_results.get("count", 0)
    active_ids: list = srp_results.get("activeResults", [])

    listings = []
    for lid in active_ids:
        item = inventory.get(str(lid))
        if item is None:
            continue
        if REQUIRE_S_TRIM and not is_cooper_s(item):
            continue
        try:
            year = item.get("year", "")

            make_raw = item.get("make", {})
            make = make_raw.get("name", "") if isinstance(make_raw, dict) else str(make_raw)

            model_raw = item.get("model", {})
            model = model_raw.get("name", "") if isinstance(model_raw, dict) else str(model_raw)

            trim_raw = item.get("trim", {})
            trim = trim_raw.get("name", "") if isinstance(trim_raw, dict) else str(trim_raw)

            price_raw = item.get("pricingDetail", {}).get("salePrice")
            price = f"${price_raw:,}" if isinstance(price_raw, int) else "Contact dealer"

            mileage_raw = item.get("mileage", {})
            mileage = (
                mileage_raw.get("value", "N/A")
                if isinstance(mileage_raw, dict)
                else str(mileage_raw or "N/A")
            )

            # Location comes from the owners table
            owner_id = str(item.get("ownerId", ""))
            owner = owners.get(owner_id, {})
            addr = owner.get("location", {}).get("address", {})
            city = addr.get("city", "")
            state = addr.get("state", "")
            location = f"{city}, {state}".strip(", ") or item.get("ownerName", "N/A")

            vdp = item.get("vdpBaseUrl", "")
            # Strip search-context query params — keep just the listing ID segment
            link = BASE_URL + vdp.split("?")[0] if vdp else "N/A"

            listings.append({
                "Year": year,
                "Model": f"{make} {model} {trim}".strip(),
                "Price": price,
                "Mileage": mileage,
                "Location": location,
                "Link": link,
            })
        except Exception:
            continue

    return listings, total


def run_search(session: requests.Session) -> list[dict]:
    all_listings: list[dict] = []
    offset = 0
    total = None
    page = 1

    while True:
        url = build_url(offset)
        print(f"Fetching page {page}...")

        resp = fetch(url, session)
        if resp is None:
            break

        html = resp.text

        if any(m in html.lower() for m in ["captcha", "cf-browser-verification", "just a moment"]):
            print("WARNING: AutoTrader returned a bot-challenge page. Results may be incomplete.")
            break

        listings, total_count = parse_page(html)

        if total is None:
            total = total_count
            print(f"  Total matching listings on AutoTrader: {total}")

        if not listings:
            if page == 1:
                print(
                    "ERROR: No listings parsed from the first page.\n"
                    "AutoTrader may have changed its page structure, or no cars match your filters.\n"
                    f"Try opening this URL in a browser:\n  {url}"
                )
            break

        print(f"  Retrieved {len(listings)} listings (running total: {len(all_listings) + len(listings)})")
        all_listings.extend(listings)
        offset += SEARCH["numRecords"]

        if offset >= total:
            break

        page += 1
        time.sleep(1.5)  # polite pause between pages

    return all_listings


def save_csv(listings: list[dict]) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"results_{timestamp}.csv"
    fields = ["Year", "Model", "Price", "Mileage", "Location", "Link"]
    with open(filename, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(listings)
    return filename


def print_table(listings: list[dict]) -> None:
    if not listings:
        print("\nNo listings to display.")
        return
    display = [
        {**r, "Link": r["Link"][:55] + "..." if len(r["Link"]) > 55 else r["Link"]}
        for r in listings
    ]
    headers = ["Year", "Model", "Price", "Mileage", "Location", "Link"]
    rows = [[r[h] for h in headers] for r in display]
    print("\n" + tabulate(rows, headers=headers, tablefmt="rounded_outline"))


def main() -> None:
    # Windows terminals default to cp1252; force UTF-8 so table borders render.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("MINI Cooper S Convertible Search")
    print("=" * 60)
    print(f"  Make/Model:   MINI Cooper S Convertible")
    print(f"  Years:        {SEARCH['startYear']}-{SEARCH['endYear']}")
    print(f"  Transmission: Automatic")
    print(f"  Max price:    ${SEARCH['maxPrice']:,}")
    print(f"  Max mileage:  {SEARCH['mileage']:,} miles")
    print(f"  Location:     within {SEARCH['searchRadius']} miles of {SEARCH['zip']}")
    print("=" * 60 + "\n")

    with requests.Session() as session:
        listings = run_search(session)

    if not listings:
        print("\nNo results retrieved. Exiting.")
        sys.exit(1)

    print(f"\nTotal listings retrieved: {len(listings)}")
    print_table(listings)

    csv_file = save_csv(listings)
    print(f"\nSaved to: {csv_file}")


if __name__ == "__main__":
    main()
