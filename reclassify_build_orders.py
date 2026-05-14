"""
One-shot retro-fix for build_orders.action_type after expanding the
doctrinal-callin coverage of classify_action() / UNIT_NAMES.

Run after the weekly scraper has released the SQLite write lock.

Logic:
  Rows where action_type='ability' but the unit name is now recognized as
  a squad (UNIT_NAMES ∪ UNIT_ALIASES) should have been classified as
  'production' under the new classifier. Flip them.

Safety notes:
  - Real abilities/upgrades (Bersaglieri Bolster, Veteran Squad Leaders,
    Crew Shock Tactics, P-47 Anti-Infantry Loiter, etc.) aren't in the
    unit-name set, so they stay 'ability'.
  - TECH_KEYWORDS-bearing names never appear in unit_names, so we don't
    accidentally flip tech actions.
  - Battlegroup picks have already been classified 'battlegroup' (not
    'ability'), so they're outside the WHERE clause.
"""

from db import get_conn
from unit_names import UNIT_NAMES, UNIT_ALIASES
from scrape_cohdb import BATTLEGROUP_NAMES


def _count(conn, sql, params):
    return conn.execute(sql, params).fetchone()[0]


def _group(conn, sql, params):
    return conn.execute(sql, params).fetchall()


def main():
    recognizable = sorted(UNIT_NAMES | set(UNIT_ALIASES.keys()))
    # BG-false-positive candidates: names that ARE recognized units but
    # NOT real battlegroup names. These were mis-tagged 'battlegroup' by
    # the old substring keyword matcher.
    bg_fp_candidates = sorted(set(recognizable) - BATTLEGROUP_NAMES)

    conn = get_conn()

    # --- Pass 1: ability -> production for recognized squads/units ---
    ph_recog = ",".join("?" * len(recognizable))
    n_ability = _count(
        conn,
        f"SELECT COUNT(*) FROM build_orders "
        f"WHERE action_type='ability' AND unit IN ({ph_recog})",
        recognizable,
    )
    print(f"Pass 1 - ability -> production: {n_ability} rows")
    if n_ability:
        rows = _group(
            conn,
            f"SELECT unit, COUNT(*) AS n FROM build_orders "
            f"WHERE action_type='ability' AND unit IN ({ph_recog}) "
            f"GROUP BY unit ORDER BY n DESC LIMIT 30",
            recognizable,
        )
        for r in rows:
            print(f"  {r['n']:5d}  {r['unit']}")
        conn.execute(
            f"UPDATE build_orders SET action_type='production' "
            f"WHERE action_type='ability' AND unit IN ({ph_recog})",
            recognizable,
        )

    # --- Pass 2: battlegroup -> production for BG false-positives ---
    ph_bgfp = ",".join("?" * len(bg_fp_candidates))
    n_bg = _count(
        conn,
        f"SELECT COUNT(*) FROM build_orders "
        f"WHERE action_type='battlegroup' AND unit IN ({ph_bgfp})",
        bg_fp_candidates,
    )
    print(f"\nPass 2 - battlegroup -> production (FP fix): {n_bg} rows")
    if n_bg:
        rows = _group(
            conn,
            f"SELECT unit, COUNT(*) AS n FROM build_orders "
            f"WHERE action_type='battlegroup' AND unit IN ({ph_bgfp}) "
            f"GROUP BY unit ORDER BY n DESC",
            bg_fp_candidates,
        )
        for r in rows:
            print(f"  {r['n']:5d}  {r['unit']}")
        conn.execute(
            f"UPDATE build_orders SET action_type='production' "
            f"WHERE action_type='battlegroup' AND unit IN ({ph_bgfp})",
            bg_fp_candidates,
        )

    conn.commit()
    print(f"\nDone. Reclassified {n_ability + n_bg} rows total.")
    conn.close()


if __name__ == "__main__":
    main()
