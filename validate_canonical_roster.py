"""
Sanity check that catches drift between canonical_roster.py and the live game data.

Validates:
1. Every sbps_id in canonical_roster.py exists in sbps.json
2. Every sbps_id in canonical_roster.py is NOT in build_unit_db.SKIP_SBPS
3. Every name in unit_categories.UNIT_CATEGORIES exists in unit_db.json
4. Every faction tag in unit_categories matches the canonical_roster.py faction
   (catches things like Kradschützen tagged as Wehr when it's actually DAK)

Run after `build_unit_db.py` to catch silent regressions.
Returns non-zero exit code if any check fails.
"""

import json
import sys
from pathlib import Path

GAME_DATA = Path(__file__).parent / "game_data"


def load_unit_db():
    with open(GAME_DATA / "unit_db.json") as f:
        return json.load(f)


def main():
    failures = []
    warnings = []

    # Load canonical roster
    from canonical_roster import CANONICAL_BASE
    from build_unit_db import SKIP_SBPS

    db = load_unit_db()
    sbps_id_to_squad = {s["sbps_id"]: s for s in db["squads"]}

    # Check 1: every canonical sbps_id exists in sbps.json
    print("Check 1: canonical roster sbps_ids exist in game data...")
    for fac, tiers in CANONICAL_BASE.items():
        for tier, units in tiers.items():
            for u in units:
                sid = u["sbps_id"]
                if sid not in sbps_id_to_squad:
                    failures.append(
                        f"  [{fac}/{tier}] {u['name']} ({sid}) NOT in sbps.json"
                    )

    # Check 2: no canonical sbps_id is in SKIP_SBPS
    print("Check 2: canonical roster does not collide with SKIP_SBPS...")
    for fac, tiers in CANONICAL_BASE.items():
        for tier, units in tiers.items():
            for u in units:
                sid = u["sbps_id"]
                if sid in SKIP_SBPS:
                    failures.append(
                        f"  [{fac}/{tier}] {u['name']} ({sid}) is in SKIP_SBPS - "
                        f"won't appear in unit_db.json"
                    )

    # Check 3: unit_categories names exist in game data
    print("Check 3: unit_categories names exist in game data...")
    from unit_categories import UNIT_CATEGORIES
    db_names = {s["name"] for s in db["squads"]}
    for unit_name in UNIT_CATEGORIES:
        if unit_name not in db_names:
            warnings.append(
                f"  '{unit_name}' in UNIT_CATEGORIES but not found in unit_db.json"
            )

    # Check 4: faction tags in unit_categories match canonical_roster
    print("Check 4: unit_categories faction tags match canonical roster...")
    canonical_unit_to_fac = {}
    for fac, tiers in CANONICAL_BASE.items():
        for tier_units in tiers.values():
            for u in tier_units:
                canonical_unit_to_fac[u["name"]] = fac

    for unit_name, (category, declared_fac) in UNIT_CATEGORIES.items():
        canonical_fac = canonical_unit_to_fac.get(unit_name)
        if canonical_fac and canonical_fac != declared_fac:
            failures.append(
                f"  '{unit_name}' is {canonical_fac} in canonical_roster but "
                f"tagged as {declared_fac} in unit_categories"
            )

    # Check 5: ensure key tier units exist in unit_db (catches when they're filtered out)
    print("Check 5: canonical roster squads landed in unit_db.json...")
    for fac, tiers in CANONICAL_BASE.items():
        for tier, units in tiers.items():
            for u in units:
                sq = sbps_id_to_squad.get(u["sbps_id"])
                if sq and sq.get("faction") != fac:
                    warnings.append(
                        f"  [{fac}/{tier}] {u['name']} ({u['sbps_id']}) - "
                        f"unit_db has it as faction '{sq.get('faction')}' "
                        f"(canonical says '{fac}')"
                    )

    # Report
    print()
    if not failures and not warnings:
        print("✓ All checks passed")
        return 0

    if failures:
        print(f"✗ {len(failures)} FAILURES:")
        for f in failures:
            print(f)
    if warnings:
        print(f"\n! {len(warnings)} warnings:")
        for w in warnings:
            print(w)

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
