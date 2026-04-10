"""
Generate a report from unit_db.json showing every unit organized by faction,
base vs battlegroup, and role. Cross-references with build_orders in the live DB
to show usage counts.
"""

import json
from pathlib import Path
from db import get_conn

UNIT_DB = Path(__file__).parent / "game_data" / "unit_db.json"


def load_db():
    with open(UNIT_DB) as f:
        return json.load(f)


def get_usage_counts():
    """Pull usage counts from build_orders table by unit name."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT unit, COUNT(*) as n
        FROM build_orders
        WHERE action_type = 'production'
        GROUP BY unit
    """).fetchall()
    conn.close()
    return {r["unit"]: r["n"] for r in rows}


def report():
    data = load_db()
    squads = data["squads"]
    battlegroups = data["battlegroups"]
    usage = get_usage_counts()

    # Group: faction -> (base | battlegroup) -> role -> [squads]
    factions = ["us", "wehr", "uk", "dak"]
    faction_label = {"us": "USF", "wehr": "WEHRMACHT", "uk": "BRITISH", "dak": "DAK"}

    for fac in factions:
        print("\n" + "=" * 70)
        print(f"  {faction_label[fac]}")
        print("=" * 70)

        fac_squads = [s for s in squads if s["faction"] == fac]

        # ----- BASE TECH TREE -----
        print("\n--- BASE TECH TREE ---")
        base = [s for s in fac_squads if not s["is_callin"]]
        by_role = {}
        for s in base:
            by_role.setdefault(s["role"], []).append(s)
        for role in sorted(by_role.keys()):
            print(f"\n  [{role.upper()}]")
            for s in sorted(by_role[role], key=lambda x: -usage.get(x["name"], 0)):
                used = usage.get(s["name"], 0)
                marker = f" ({used} games)" if used else ""
                print(f"    {s['name']}{marker}")

        # ----- BATTLEGROUP CALL-INS -----
        bg_units = [s for s in fac_squads if s["is_callin"]]
        if bg_units:
            print("\n--- BATTLEGROUP CALL-INS ---")
            by_bg = {}
            for s in bg_units:
                by_bg.setdefault(s["battlegroup"], []).append(s)
            for bg_id in sorted(by_bg.keys()):
                bg_info = battlegroups.get(bg_id, {})
                bg_name = bg_info.get("display_name", bg_id)
                print(f"\n  >> {bg_name}")
                for s in sorted(by_bg[bg_id], key=lambda x: -usage.get(x["name"], 0)):
                    used = usage.get(s["name"], 0)
                    marker = f" ({used} games)" if used else ""
                    print(f"    {s['name']} [{s['role']}]{marker}")

    # ----- COVERAGE CHECK -----
    print("\n" + "=" * 70)
    print("  COVERAGE: Units in our build_orders not matched to game data")
    print("=" * 70)
    db_names = {s["name"] for s in squads}
    missing = sorted(
        [(unit, n) for unit, n in usage.items() if unit not in db_names],
        key=lambda x: -x[1],
    )
    if missing:
        print(f"\n  {len(missing)} unit names from build_orders are not in the game data:")
        for unit, n in missing[:30]:
            print(f"    {unit}: {n} games")
        if len(missing) > 30:
            print(f"    ... and {len(missing) - 30} more")
    else:
        print("  All units matched!")


if __name__ == "__main__":
    report()
