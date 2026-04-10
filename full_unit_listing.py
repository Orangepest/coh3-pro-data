"""
Print my full understanding of every CoH3 unit.
Filters out internal/duplicate entries and groups cleanly by faction → BG → role.
"""

import json
from pathlib import Path
from db import get_conn

UNIT_DB = Path(__file__).parent / "game_data" / "unit_db.json"

# Filter rules
INTERNAL_NAMES = {"sp", "specialist", "specialists", "parent_pbg",
                  "mass_production", "infantry_assault"}


def is_internal(name: str, sbps_id: str) -> bool:
    if name in INTERNAL_NAMES:
        return True
    if name.islower() and "_" in name:
        return True
    if sbps_id.endswith("_sp") or "_sp_" in sbps_id:
        return True
    if "_loiter_" in sbps_id or sbps_id.startswith("partisan_tunnel"):
        return True
    if sbps_id.startswith("medic_"):  # medic squads aren't really "units"
        return False  # actually let's keep them
    return False


def is_duplicate_variant(sq, all_squads):
    """Skip clearly redundant variant entries (recrewable, africa, 3man, paradrop)."""
    sid = sq["sbps_id"]
    # Skip africa variants - the regular variant exists
    if sid.endswith("_africa_uk"):
        base_id = sid.replace("_africa_uk", "_uk")
        if any(s["sbps_id"] == base_id for s in all_squads):
            return True
    # Skip recrewable variants - they're the same unit when picked up
    if "_recrew" in sid:
        return True
    # Skip 3man variants
    if "_3man_" in sid or "_3_man_" in sid:
        return True
    # Skip paradrop variants - we want the base unit shown once
    if "_paradrop_" in sid:
        return True
    return False


def load_data():
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


def usage_for(name, usage):
    n = usage.get(name, 0)
    return f" ({n})" if n else ""


def main():
    data = load_data()
    squads = data["squads"]
    bgs = data["battlegroups"]
    usage = get_usage()

    # Filter
    clean = [s for s in squads if not is_internal(s["name"], s["sbps_id"])]
    clean = [s for s in clean if not is_duplicate_variant(s, squads)]

    # Dedup by (name, faction) - prefer non-callin if both
    from collections import defaultdict
    by_key = defaultdict(list)
    for s in clean:
        by_key[(s["name"], s["faction"])].append(s)

    deduped = []
    for entries in by_key.values():
        # Prefer dual_availability > callin > base
        entries.sort(key=lambda x: (
            0 if x.get("dual_availability") else (1 if x["is_callin"] else 2)
        ))
        deduped.append(entries[0])

    factions = ["us", "wehr", "uk", "dak"]
    faction_label = {
        "us": "USF (Americans)",
        "wehr": "WEHRMACHT",
        "uk": "BRITISH FORCES",
        "dak": "DAK (Afrika Korps)",
    }
    role_order = ["infantry", "team_weapons", "vehicles", "emplacements"]
    role_label = {
        "infantry": "Infantry",
        "team_weapons": "Team Weapons",
        "vehicles": "Vehicles",
        "emplacements": "Emplacements / Buildings",
    }

    for fac in factions:
        print()
        print("=" * 75)
        print(f"  {faction_label[fac]}")
        print("=" * 75)

        fac_units = [s for s in deduped if s["faction"] == fac]

        # === BASE TECH TREE ===
        base = [s for s in fac_units if not s["is_callin"]]
        print("\n  --- BASE TECH TREE ---")
        for role in role_order:
            in_role = [s for s in base if s["role"] == role]
            if not in_role:
                continue
            print(f"\n    {role_label[role]}:")
            for s in sorted(in_role, key=lambda x: -usage.get(x["name"], 0)):
                print(f"      {s['name']}{usage_for(s['name'], usage)}")

        # === DUAL AVAILABILITY ===
        dual = [s for s in fac_units if s.get("dual_availability")]
        if dual:
            print("\n  --- DUAL (BASE + BG UNLOCK) ---")
            for s in sorted(dual, key=lambda x: -usage.get(x["name"], 0)):
                bg_name = bgs.get(s["battlegroup"], {}).get("display_name", s["battlegroup"])
                print(f"      {s['name']} [{role_label.get(s['role'], s['role'])}] - unlocked via {bg_name}{usage_for(s['name'], usage)}")

        # === BATTLEGROUP CALL-INS ===
        callins = [s for s in fac_units if s["is_callin"] and not s.get("dual_availability")]
        if callins:
            print("\n  --- BATTLEGROUP CALL-INS ---")
            by_bg = defaultdict(list)
            for s in callins:
                by_bg[s["battlegroup"]].append(s)
            for bg_id in sorted(by_bg.keys(),
                                key=lambda b: bgs.get(b, {}).get("display_name", b)):
                bg_name = bgs.get(bg_id, {}).get("display_name", bg_id)
                print(f"\n    >> {bg_name}")
                for s in sorted(by_bg[bg_id], key=lambda x: -usage.get(x["name"], 0)):
                    print(f"      {s['name']} [{role_label.get(s['role'], s['role'])}]{usage_for(s['name'], usage)}")

    # === BATTLEGROUPS BY FACTION ===
    print("\n\n" + "=" * 75)
    print("  ALL BATTLEGROUPS")
    print("=" * 75)
    by_fac = defaultdict(list)
    for bg_id, bg in bgs.items():
        by_fac[bg.get("faction", "?")].append((bg_id, bg.get("display_name", bg_id)))
    for fac in factions:
        print(f"\n  {faction_label[fac]}:")
        for _, name in sorted(by_fac.get(fac, []), key=lambda x: x[1]):
            print(f"    - {name}")


if __name__ == "__main__":
    main()
