"""
Direct-fetch winner-side recovery for cohdb_replays that fell outside the
cohdb match-listing window. Hits /replays/<id> per replay (vs the listing
endpoint that backfill_winners.py uses), extracts winner + per-player
faction/side from the page markup.

These are the ~5,000 older replays brought in by gap-fill that aren't in
cohdb's current listing pagination anymore.

Concurrent: 4 workers for HTTP, serialized DB writes.
"""

import re
import sys
import time
import html
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from db import get_conn
from config import REQUEST_DELAY, MAX_RETRIES
from backfill_winners import (
    SIDE_OF_FACTION,
    FACTION_SLUG_NORMALIZE,
    FACTION_IMG_RE,
    PLAYER_LINK_RE,
    store_match_result,
)

# The imported VICTOR_RE from backfill_winners.py is tuned for the listing-
# row markup (`text-sm font-medium`). Individual replay pages use a different
# class set (`text-2xl font-bold text-orange-400` etc). Use a looser pattern
# that catches both.
VICTOR_RE = re.compile(
    r'<span class="hidden[^"]*">\s*(Allies|Axis)\s*</span>'
)


COHDB_BASE = "https://cohdb.com"
WORKERS = 4
COMMIT_EVERY = 50


def fetch_replay_page(rid):
    """Worker: fetch /replays/<rid>, parse winner + players.
    Returns (rid, match_dict_or_None, error_or_None)."""
    url = f"{COHDB_BASE}/replays/{rid}"
    headers = {"User-Agent": "CoH3ProAnalysis/1.0"}
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, timeout=30, headers=headers)
            if resp.status_code == 404:
                return (rid, None, "404")
            resp.raise_for_status()
            page = resp.text

            victor = VICTOR_RE.search(page)
            if not victor:
                return (rid, None, "no_victor_in_page")

            factions = FACTION_IMG_RE.findall(page)
            if len(factions) < 2:
                return (rid, None, f"only_{len(factions)}_factions")

            names = PLAYER_LINK_RE.findall(page)

            p1_faction = FACTION_SLUG_NORMALIZE.get(factions[0], factions[0])
            p2_faction = FACTION_SLUG_NORMALIZE.get(factions[1], factions[1])
            p1_side = SIDE_OF_FACTION.get(p1_faction, "?")
            p2_side = SIDE_OF_FACTION.get(p2_faction, "?")
            winner_side = victor.group(1).lower()

            p1_name = html.unescape(names[0]).strip() if len(names) > 0 else None
            p2_name = html.unescape(names[1]).strip() if len(names) > 1 else None

            match = {
                "replay_id": rid,
                "winner_side": winner_side,
                "players": [
                    {"name": p1_name, "faction_slug": p1_faction, "side": p1_side,
                     "won": 1 if p1_side == winner_side else 0},
                    {"name": p2_name, "faction_slug": p2_faction, "side": p2_side,
                     "won": 1 if p2_side == winner_side else 0},
                ],
            }
            return (rid, match, None)
        except requests.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(REQUEST_DELAY * (attempt + 1))
            else:
                return (rid, None, str(e))
    return (rid, None, "all_retries_failed")


def main():
    conn = get_conn()
    rows = conn.execute("""
        SELECT replay_id FROM cohdb_replays
        WHERE winner_side IS NULL AND mode = 'ranked_1v1'
        ORDER BY replay_id DESC
    """).fetchall()
    rids = [r["replay_id"] for r in rows]
    print(f"Recovering winner data for {len(rids)} replays...\n", flush=True)

    n_recovered = 0
    n_no_victor = 0
    n_404 = 0
    n_api_fail = 0
    n_other = 0
    start = time.monotonic()

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(fetch_replay_page, rid): rid for rid in rids}
        for i, fut in enumerate(as_completed(futures), 1):
            rid, match, err = fut.result()
            if err == "404":
                n_404 += 1
            elif err == "no_victor_in_page":
                n_no_victor += 1
            elif err and err.startswith("only_"):
                n_other += 1
            elif err:
                n_api_fail += 1
            elif match:
                store_match_result(match, conn)
                n_recovered += 1

            if i % COMMIT_EVERY == 0:
                conn.commit()
                elapsed = time.monotonic() - start
                rate = i / elapsed
                eta = (len(rids) - i) / rate if rate else 0
                print(
                    f"  [{i}/{len(rids)}] recovered={n_recovered} no-victor={n_no_victor} "
                    f"404={n_404} api-fail={n_api_fail} other={n_other}  "
                    f"rate={rate:.1f}/s eta={eta:.0f}s",
                    flush=True,
                )

    conn.commit()
    elapsed = time.monotonic() - start
    print(f"\n=== DONE in {elapsed:.0f}s ===", flush=True)
    print(f"  recovered:    {n_recovered}", flush=True)
    print(f"  no victor:    {n_no_victor}", flush=True)
    print(f"  404'd:        {n_404}", flush=True)
    print(f"  api failure:  {n_api_fail}", flush=True)
    print(f"  other:        {n_other}", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
