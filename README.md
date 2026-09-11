# mini-search-tool

A Python CLI tool that searches AutoTrader.com for used MINI Cooper Convertibles matching specific criteria and prints the results as a table, then saves them to a CSV file.

## Search criteria (hardcoded)

| Filter        | Value                        |
|---------------|------------------------------|
| Make / Model  | MINI Cooper Convertible      |
| Body style    | Convertible                  |
| Years         | 2022 – 2025                  |
| Transmission  | Automatic                    |
| Max price     | $30,000                      |
| Max mileage   | 40,000 miles                 |
| Location      | Within 500 miles of zip 95008 |
| Listing type  | Used                         |

## Requirements

- Python 3.10+ (use `py` on Windows)
- pip packages listed in `requirements.txt`

## Setup

```powershell
# Install dependencies
py -m pip install -r requirements.txt
```

## Usage

```powershell
py search_minis.py
```

The script will:
1. Fetch one or more result pages from AutoTrader
2. Parse listings from the embedded JSON payload (falling back to HTML parsing if needed)
3. Print a formatted table in the terminal
4. Save a timestamped `results_YYYYMMDD_HHMMSS.csv` file in the current directory

## Output example

```
MINI Cooper Convertible Search
============================================================
  Years:       2022–2025
  Transmission: Automatic
  Max price:   $30,000
  Max mileage: 40,000 miles
  Zip:         95008 (within 500 miles)
============================================================

Fetching page 1...
  Found 18 listings on this page (parsed via JSON).

Total listings found: 18

╭──────┬────────────────────┬──────────┬──────────┬──────────────────┬─────────────────────╮
│ Year │ Model              │ Price    │ Mileage  │ Location         │ Link                │
├──────┼────────────────────┼──────────┼──────────┼──────────────────┼─────────────────────┤
│ 2023 │ MINI Cooper S Conv │ $28,500  │ 12,345   │ San Jose, CA     │ https://…           │
╰──────┴────────────────────┴──────────┴──────────┴──────────────────┴─────────────────────╯

Results saved to: results_20260910_143022.csv
```

## Error handling

| Situation                          | What the script does                                      |
|------------------------------------|-----------------------------------------------------------|
| No internet connection             | Prints a clear error and exits                            |
| AutoTrader returns HTTP 403 / 429  | Prints a human-readable message (bot-block or rate-limit) |
| Bot-challenge / CAPTCHA page       | Warns that results may be incomplete                      |
| Page structure changed             | Falls back from JSON parser to HTML parser; warns if both fail |
| No matching listings               | Prints a message and exits cleanly                        |

## Notes

- AutoTrader is a JavaScript-rendered SPA. The script targets the `__NEXT_DATA__` JSON blob embedded in the page source, which is more stable than scraping raw HTML elements.
- If AutoTrader updates its site significantly, the JSON path inside `extract_listings_from_json()` may need updating.
- Be considerate: the script waits 1 second between paginated requests.
