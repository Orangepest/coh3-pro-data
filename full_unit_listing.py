"""
Print canonical CoH3 unit listing organized by faction → tier → role.
Uses canonical_roster.py as the source of truth for base, with battlegroup
call-ins layered on top.
"""

import json
from collections import defaultdict
from pathlib import Path

from db import get_conn
from canonical_roster import CANONICAL_BASE, DAK_CALLIN_TREE

UNIT_DB = Path(__file__).parent / "game_data" / "unit_db.json"


def load_db():
    with open(UNIT_DB) as f:
        return json.load(f)


def get_usage():
    conn = get_conn()
    rows = conn.execute("""
        SELECT unit, COUNT(*) n FROM build_orders
        WHERE action_type = 'production'
        GROUP BY unit
    """).fetchall()
    conn.close()
    return {r["unit"]: r["n"] for r in rows}


def usage_str(name, usage):
    n = usage.get(name, 0)
    return f" ({n})" if n else ""


def main():
    db = load_db()
    bgs = db["battlegroups"]
    usage = get_usage()

    factions = ["us", "wehr", "uk", "dak"]
    faction_label = {
        "us": "USF (Americans)",
        "wehr": "WEHRMACHT",
        "uk": "BRITISH FORCES",
        "dak": "DAK (Afrika Korps)",
    }
    tier_label = {
        "t0": "T0 / HQ",
        "t1": "T1",
        "t2": "T2",
        "t3": "T3",
        "t4": "T4",
    }

    for fac in factions:
        print()
        print("=" * 75)
        print(f"  {faction_label[fac]}")
        print("=" * 75)

        # ===== BASE TECH TREE (from canonical roster) =====
        print("\n  --- BASE TECH TREE ---")
        for tier in ["t0", "t1", "t2", "t3", "t4"]:
            units = CANONICAL_BASE[fac].get(tier, [])
            if not units:
                continue
            free = [u for u in units if not u.get("tier_upgrade_locked")]
            locked = [u for u in units if u.get("tier_upgrade_locked")]
            print(f"\n    {tier_label[tier]}:")
            for u in free:
                print(f"      {u['name']}{usage_str(u['name'], usage)}")
            if locked:
                print(f"      [tier upgrade unlocks:]")
                for u in locked:
                    print(f"        {u['name']}{usage_str(u['name'], usage)}")

        # ===== DAK SPECIAL: T0 CALLIN TREE =====
        if fac == "dak":
            print("\n  --- T0 CALLIN TREE ---")
            print("\n    Base callins (from HQ abilities):")
            for u in DAK_CALLIN_TREE["base"]:
                print(f"      {u}")
            print("\n    [T4 upgrade transforms callins into:]")
            for u in DAK_CALLIN_TREE["t4_upgraded"]:
                print(f"      {u}")

        # ===== BATTLEGROUP CALL-INS =====
        # All squads in this faction that are flagged as callins
        fac_callins = [
            s for s in db["squads"]
            if s["faction"] == fac and s["is_callin"]
        ]

        if fac_callins:
            duals = [s for s in fac_callins if s.get("dual_availability")]
            bg_unlocks = [s for s in fac_callins if s.get("bg_unlocks_production") and not s.get("dual_availability")]
            pure_callins = [s for s in fac_callins
                           if not s.get("dual_availability")
                           and not s.get("bg_unlocks_production")]

            if duals:
                print("\n  --- DUAL (base AND BG callin, both available independently) ---")
                seen = set()
                for s in sorted(duals, key=lambda x: -usage.get(x["name"], 0)):
                    key = (s["name"], s.get("battlegroup"))
                    if key in seen:
                        continue
                    seen.add(key)
                    bg_name = bgs.get(s["battlegroup"], {}).get("display_name") or s.get("battlegroup", "?")
                    tier = s.get("tier")
                    tier_str = f" [base {tier.upper()}]" if tier else ""
                    print(f"      {s['name']}{tier_str} - also via {bg_name}{usage_str(s['name'], usage)}")

            if bg_unlocks:
                print("\n  --- BG UNLOCKS BASE PRODUCTION (BG-only, but produced from base after pick) ---")
                seen = set()
                for s in sorted(bg_unlocks, key=lambda x: -usage.get(x["name"], 0)):
                    key = (s["name"], s.get("battlegroup"))
                    if key in seen:
                        continue
                    seen.add(key)
                    bg_name = bgs.get(s["battlegroup"], {}).get("display_name") or s.get("battlegroup", "?")
                    print(f"      {s['name']} - unlocked by {bg_name}{usage_str(s['name'], usage)}")

            if pure_callins:
                print("\n  --- BATTLEGROUP CALL-INS (one-shot ability spawns) ---")
                by_bg = defaultdict(list)
                for s in pure_callins:
                    by_bg[s["battlegroup"]].append(s)
                for bg_id in sorted(
                    by_bg.keys(),
                    key=lambda b: (bgs.get(b, {}).get("display_name") or b or "")
                ):
                    bg_name = bgs.get(bg_id, {}).get("display_name") or bg_id
                    print(f"\n    >> {bg_name}")
                    seen = set()
                    for s in sorted(by_bg[bg_id], key=lambda x: -usage.get(x["name"], 0)):
                        if s["name"] in seen:
                            continue
                        seen.add(s["name"])
                        print(f"      {s['name']} [{s['role']}]{usage_str(s['name'], usage)}")


if __name__ == "__main__":
    main()
