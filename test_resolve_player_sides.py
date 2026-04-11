"""
Tests for resolve_player_sides.py — the pipeline that maps build_orders
player_name to (faction, side, won) via name match + faction inference fallback.

Run with: python3 test_resolve_player_sides.py
"""

import os
import tempfile
import unittest

# Point the project at a temp DB BEFORE importing any project modules.
_TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP_DB.close()
os.environ["COH3DATA_DB_PATH"] = _TMP_DB.name

# Now safe to import
import db  # noqa: E402
import resolve_player_sides as rps  # noqa: E402


def _seed_replay(conn, replay_id, winner_side, players):
    """Insert a replay and its cohdb_replay_players + build_orders rows.

    players: list of dicts with keys
        name (str), slug (str|None), side (str|None), won (int|None),
        register_in_crp (bool, default True), units (list[str], default [])
    """
    conn.execute(
        "INSERT OR REPLACE INTO cohdb_replays (replay_id, map_name, mode, winner_side) "
        "VALUES (?, ?, '1v1', ?)",
        (replay_id, "test_map", winner_side),
    )
    for p in players:
        if p.get("register_in_crp", True):
            conn.execute(
                "INSERT INTO cohdb_replay_players "
                "(replay_id, player_name, faction_slug, side, won) VALUES (?,?,?,?,?)",
                (replay_id, p["name"], p.get("slug"), p.get("side"), p.get("won")),
            )
        for u in p.get("units", []):
            conn.execute(
                "INSERT INTO build_orders "
                "(replay_id, player_name, seconds, unit, action_type) "
                "VALUES (?, ?, 0, ?, 'production')",
                (replay_id, p["name"], u),
            )
    conn.commit()


class InferFactionTests(unittest.TestCase):
    """Pure-function tests on rps.infer_faction()."""

    def test_clear_us_majority(self):
        units = ["Riflemen Squad", "Riflemen Squad", "M1 Mortar Team"]
        self.assertEqual(rps.infer_faction(units), "us")

    def test_clear_wehr_majority(self):
        units = ["Grenadier Squad", "MG 42 Machine Gun Team", "Pioneer Squad"]
        self.assertEqual(rps.infer_faction(units), "wehr")

    def test_clear_dak_majority(self):
        units = [
            "Panzerpioneer Squad",
            "Kradschützen Motorcycle Team",
            "Assault Grenadier Squad",
        ]
        self.assertEqual(rps.infer_faction(units), "dak")

    def test_clear_uk_majority(self):
        units = ["Infantry Section", "Infantry Section", "Royal Engineer Section"]
        self.assertEqual(rps.infer_faction(units), "uk")

    def test_empty_units_returns_none(self):
        self.assertIsNone(rps.infer_faction([]))

    def test_only_unknown_units_returns_none(self):
        self.assertIsNone(rps.infer_faction(["totally fake unit", "another fake"]))

    def test_only_ambiguous_units_returns_none(self):
        # "Sniper" is in AMBIGUOUS_SHARED_NAMES (USF + Wehr) — must be excluded
        # from UNIT_TO_FACTION so it cannot bias inference. Same for the other
        # ambiguous shared names.
        from canonical_roster import AMBIGUOUS_SHARED_NAMES

        for n in AMBIGUOUS_SHARED_NAMES:
            self.assertNotIn(
                n,
                rps.UNIT_TO_FACTION,
                f"{n!r} must be excluded from UNIT_TO_FACTION (it's ambiguous)",
            )
        self.assertIsNone(rps.infer_faction(list(AMBIGUOUS_SHARED_NAMES)))

    def test_mixed_factions_picks_majority(self):
        # 3 Wehr units + 1 US unit -> Wehr wins
        units = [
            "Grenadier Squad",
            "MG 42 Machine Gun Team",
            "Pioneer Squad",
            "Riflemen Squad",
        ]
        self.assertEqual(rps.infer_faction(units), "wehr")


class ResolveAllTests(unittest.TestCase):
    """End-to-end tests on rps.resolve_all() against a temp SQLite DB."""

    def setUp(self):
        # Fresh schema each test
        if os.path.exists(_TMP_DB.name):
            os.remove(_TMP_DB.name)
        db.init_db()
        self.conn = db.get_conn()

    def tearDown(self):
        self.conn.close()

    def test_name_match_path(self):
        """A player whose name matches an entry in cohdb_replay_players
        should be resolved via 'name_match' with the slug-mapped faction."""
        _seed_replay(
            self.conn,
            replay_id=1,
            winner_side="allies",
            players=[
                {
                    "name": "AlicePlayer",
                    "slug": "americans",
                    "side": "allies",
                    "won": 1,
                    "units": ["Riflemen Squad"],
                },
                {
                    "name": "BobPlayer",
                    "slug": "germans",
                    "side": "axis",
                    "won": 0,
                    "units": ["Grenadier Squad"],
                },
            ],
        )
        rps.resolve_all()

        rows = self.conn.execute(
            "SELECT player_name, faction, side, won, resolved_via "
            "FROM build_orders_player_resolved ORDER BY player_name"
        ).fetchall()
        self.assertEqual(len(rows), 2)
        alice, bob = rows
        self.assertEqual(alice["player_name"], "AlicePlayer")
        self.assertEqual(alice["faction"], "us")
        self.assertEqual(alice["side"], "allies")
        self.assertEqual(alice["won"], 1)
        self.assertEqual(alice["resolved_via"], "name_match")
        self.assertEqual(bob["faction"], "wehr")
        self.assertEqual(bob["side"], "axis")
        self.assertEqual(bob["won"], 0)
        self.assertEqual(bob["resolved_via"], "name_match")

    def test_faction_inference_fallback(self):
        """When the build_orders player_name doesn't match cohdb_replay_players,
        the unit list should be used to infer the faction and assign side/won."""
        _seed_replay(
            self.conn,
            replay_id=2,
            winner_side="axis",
            players=[
                {
                    "name": "RegisteredOne",
                    "slug": "afrika_korps",
                    "side": "axis",
                    "won": 1,
                    "units": ["Panzerpioneer Squad"],
                },
                {
                    "name": "RegisteredTwo",
                    "slug": "british",
                    "side": "allies",
                    "won": 0,
                    "units": ["Royal Engineer Section"],
                },
                # build_orders has a player whose name is NOT in crp at all
                {
                    "name": "MysteryName",
                    "register_in_crp": False,
                    "units": [
                        "Panzerpioneer Squad",
                        "Kradschützen Motorcycle Team",
                        "Assault Grenadier Squad",
                    ],
                },
            ],
        )
        rps.resolve_all()

        mystery = self.conn.execute(
            "SELECT * FROM build_orders_player_resolved WHERE player_name='MysteryName'"
        ).fetchone()
        self.assertIsNotNone(mystery)
        self.assertEqual(mystery["resolved_via"], "faction_inference")
        self.assertEqual(mystery["faction"], "dak")
        self.assertEqual(mystery["side"], "axis")
        # winner_side was 'axis', inferred side was 'axis' -> won = 1
        self.assertEqual(mystery["won"], 1)

    def test_faction_inference_loss_when_side_doesnt_match_winner(self):
        _seed_replay(
            self.conn,
            replay_id=3,
            winner_side="allies",
            players=[
                {
                    "name": "Anchor",
                    "slug": "americans",
                    "side": "allies",
                    "won": 1,
                    "units": ["Riflemen Squad"],
                },
                {
                    "name": "GhostPlayer",
                    "register_in_crp": False,
                    "units": ["Grenadier Squad", "MG 42 Machine Gun Team"],
                },
            ],
        )
        rps.resolve_all()

        ghost = self.conn.execute(
            "SELECT * FROM build_orders_player_resolved WHERE player_name='GhostPlayer'"
        ).fetchone()
        self.assertEqual(ghost["resolved_via"], "faction_inference")
        self.assertEqual(ghost["faction"], "wehr")
        self.assertEqual(ghost["side"], "axis")
        # winner was allies, ghost is axis -> lost
        self.assertEqual(ghost["won"], 0)

    def test_unresolved_when_no_recognizable_units(self):
        _seed_replay(
            self.conn,
            replay_id=4,
            winner_side="allies",
            players=[
                {
                    "name": "Anchor",
                    "slug": "americans",
                    "side": "allies",
                    "won": 1,
                    "units": ["Riflemen Squad"],
                },
                {
                    "name": "Garbled",
                    "register_in_crp": False,
                    "units": ["totally fake unit", "another fake"],
                },
            ],
        )
        rps.resolve_all()

        garbled = self.conn.execute(
            "SELECT * FROM build_orders_player_resolved WHERE player_name='Garbled'"
        ).fetchone()
        self.assertEqual(garbled["resolved_via"], "unresolved")
        self.assertIsNone(garbled["faction"])
        self.assertIsNone(garbled["side"])
        self.assertIsNone(garbled["won"])

    def test_unknown_slug_stored_as_null_faction_but_still_resolved(self):
        """If cohdb hands us a faction_slug we don't recognize, the row should
        still resolve via name_match with the side/won copied through, but
        faction stays NULL until FACTION_TO_SLUGS is updated."""
        _seed_replay(
            self.conn,
            replay_id=5,
            winner_side="allies",
            players=[
                {
                    "name": "WeirdSlug",
                    "slug": "martian_reich",  # not in FACTION_TO_SLUGS
                    "side": "axis",
                    "won": 0,
                    "units": ["Grenadier Squad"],
                },
                {
                    "name": "NormalAllied",
                    "slug": "americans",
                    "side": "allies",
                    "won": 1,
                    "units": ["Riflemen Squad"],
                },
            ],
        )
        rps.resolve_all()

        weird = self.conn.execute(
            "SELECT * FROM build_orders_player_resolved WHERE player_name='WeirdSlug'"
        ).fetchone()
        self.assertEqual(weird["resolved_via"], "name_match")
        self.assertIsNone(weird["faction"])  # unknown slug -> NULL
        self.assertEqual(weird["side"], "axis")
        self.assertEqual(weird["won"], 0)

    def test_replays_without_winner_side_are_skipped(self):
        """resolve_all() only walks replays where cohdb_replays.winner_side IS NOT NULL."""
        _seed_replay(
            self.conn,
            replay_id=6,
            winner_side=None,
            players=[
                {
                    "name": "ShouldNotAppear",
                    "slug": "americans",
                    "side": "allies",
                    "won": 1,
                    "units": ["Riflemen Squad"],
                },
            ],
        )
        rps.resolve_all()

        rows = self.conn.execute(
            "SELECT * FROM build_orders_player_resolved WHERE player_name='ShouldNotAppear'"
        ).fetchall()
        self.assertEqual(rows, [])

    def test_resolve_all_is_idempotent(self):
        """Running twice should not duplicate rows; the table is wiped on each run."""
        _seed_replay(
            self.conn,
            replay_id=7,
            winner_side="allies",
            players=[
                {
                    "name": "Idem",
                    "slug": "americans",
                    "side": "allies",
                    "won": 1,
                    "units": ["Riflemen Squad"],
                },
            ],
        )
        rps.resolve_all()
        first = self.conn.execute(
            "SELECT COUNT(*) FROM build_orders_player_resolved"
        ).fetchone()[0]
        rps.resolve_all()
        second = self.conn.execute(
            "SELECT COUNT(*) FROM build_orders_player_resolved"
        ).fetchone()[0]
        self.assertEqual(first, second)


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        if os.path.exists(_TMP_DB.name):
            os.remove(_TMP_DB.name)
