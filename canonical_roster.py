"""
SHARED CONSTANTS used by multiple modules:
- AMBIGUOUS_SHARED_NAMES: unit names that appear in multiple factions

Hand-curated canonical base tech tree for CoH3 1v1 multiplayer.

This is the source of truth - typed by a pro player from memory.
Use this instead of trying to filter the messy cohstats game data.

Format: faction -> tier -> list of unit dicts
Each unit has: name (game data screen_name), sbps_id (canonical), and optional flags.

Tier semantics:
  t0 = HQ-level units (always available from start)
  t1 = First base building tier
  t2 = Second base building tier
  t3 = Third base building tier
  t4 = Fourth/top base building tier

Special flags:
  tier_upgrade_locked = unit requires the tier's upgrade unlock (not free)
  vehicle_upgrade_path = unit is a vehicle weapon upgrade variant of another base unit
"""

# Single source of truth for unit names that exist on multiple factions.
# Imported by analyze.py, resolve_player_sides.py, and build_classifier_data.py
# so they all stay in sync.
AMBIGUOUS_SHARED_NAMES: set[str] = {
    "8 Rad Armored Car",      # DAK base T2 + Wehr Mechanized BG callin
    "Panzergrenadier Squad",  # DAK T0 mainline (palmgren) + Wehr T3 elite
    "Sniper",                 # USF T2 + Wehr T1
    "Tiger Heavy Tank",       # Wehr Breakthrough BG + DAK T0 callin tree
}


CANONICAL_BASE = {
    # =================================================================
    # USF (Americans)
    # =================================================================
    "us": {
        "t0": [
            {"name": "Engineer Squad", "sbps_id": "engineer_us"},
            {"name": "Scout Squad", "sbps_id": "scout_us"},
            {"name": "Captain Retinue", "sbps_id": "captain_us"},
        ],
        "t1": [
            {"name": "Riflemen Squad", "sbps_id": "riflemen_us"},
            {"name": "1\u20444-ton 4x4 Truck", "sbps_id": "truck_4x4_us"},  # Jeep
            {"name": "M1 Mortar Team", "sbps_id": "mortar_81mm_us"},
        ],
        "t2": [
            {"name": "Bazooka Squad", "sbps_id": "bazooka_team_us"},
            {"name": "Sniper", "sbps_id": "sniper_us"},
            {"name": "M3 Armored Personnel Carrier", "sbps_id": "halftrack_us"},
            {"name": "M1919 Machine Gun Team", "sbps_id": "hmg_30cal_us"},
        ],
        "t3": [
            {"name": "M8 Greyhound Armored Car", "sbps_id": "greyhound_us"},
            {"name": "M1 Anti-tank Gun Team", "sbps_id": "at_gun_57mm_us"},
            {"name": "M24 Chaffee Light Tank", "sbps_id": "chaffee_us"},
        ],
        "t4": [
            {"name": "M4A1 Sherman Medium Tank", "sbps_id": "sherman_us"},
            {"name": "M4(105) Sherman Bulldozer", "sbps_id": "sherman_bulldozer_us"},
            {"name": "M18 Hellcat Tank Destroyer", "sbps_id": "hellcat_us"},
        ],
    },

    # =================================================================
    # Wehrmacht
    # =================================================================
    "wehr": {
        "t0": [
            {"name": "Pioneer Squad", "sbps_id": "pioneer_ger"},
            {"name": "Kettenkrad Recon Vehicle", "sbps_id": "kettenkrad_ger"},
        ],
        "t1": [
            {"name": "Grenadier Squad", "sbps_id": "grenadier_ger"},
            {"name": "GrW 34 Mortar Team", "sbps_id": "mortar_81mm_ger"},
            {"name": "Sniper", "sbps_id": "sniper_ger"},
            {"name": "MG 42 Machine Gun Team", "sbps_id": "hmg_mg42_ger"},
        ],
        "t2": [
            {"name": "Jäger Squad", "sbps_id": "jaeger_ger"},
            {"name": "Flak 30 Anti-aircraft Gun Team", "sbps_id": "aa_gun_20mm_ger"},
            {"name": "221 Scout Car", "sbps_id": "armored_car_ger"},
            {"name": "Marder III M Tank Destroyer", "sbps_id": "marder_iii_ger",
             "tier_upgrade_locked": True},
            {"name": "Wirbelwind Flakpanzer", "sbps_id": "wirbelwind_ger",
             "tier_upgrade_locked": True},
        ],
        "t3": [
            {"name": "Panzergrenadier Squad", "sbps_id": "panzergrenadier_ger"},
            {"name": "Pak 40 Anti-tank Gun Team", "sbps_id": "at_gun_75mm_ger"},
            {"name": "251 Medium Carrier", "sbps_id": "halftrack_ger"},
            {"name": "StuG III G Assault Gun", "sbps_id": "stug_iii_ger",
             "tier_upgrade_locked": True},
            {"name": "Nebelwerfer 42 Rocket Launcher Team", "sbps_id": "nebelwerfer_150mm_ger",
             "tier_upgrade_locked": True},
        ],
        "t4": [
            {"name": "Stoßtruppen Squad", "sbps_id": "stormtrooper_ger"},
            {"name": "Sturmpanzer IV Brummbär", "sbps_id": "brummbar_ger"},
            {"name": "Panzer IV Medium Tank", "sbps_id": "panzer_iv_ger"},
        ],
    },

    # =================================================================
    # DAK (Afrika Korps)
    # =================================================================
    "dak": {
        "t0": [
            {"name": "250 Light Carrier", "sbps_id": "halftrack_250_ak"},
            {"name": "Panzergrenadier Squad", "sbps_id": "panzergrenadier_ak"},
            {"name": "Panzerpioneer Squad", "sbps_id": "panzerpioneer_ak"},
            {"name": "Kradschützen Motorcycle Team", "sbps_id": "kradschutzen_motorcycle_ak"},
        ],
        "t1": [
            {"name": "Assault Grenadier Squad", "sbps_id": "assault_panzergrenadier_ak"},
            {"name": "Panzerjäger Squad", "sbps_id": "panzerjaeger_inf_ak"},
            {"name": "MG34 Team", "sbps_id": "hmg_mg34_ak"},
            {"name": "Pak 38 Anti-tank Gun Team", "sbps_id": "at_gun_50mm_pak_38_ak"},
            {"name": "Flakvierling Half-track", "sbps_id": "halftrack_7_flak_ak",
             "tier_upgrade_locked": True},
            {"name": "le.IG 18 Support Gun Team", "sbps_id": "leig_75mm_ak",
             "tier_upgrade_locked": True},
        ],
        "t2": [
            {"name": "8 Rad Armored Car", "sbps_id": "armored_car_8_rad_ak"},
            {"name": "Marder III Tank Destroyer", "sbps_id": "marder_iii_ak"},
            {"name": "254 Reconnaissance Tractor", "sbps_id": "armored_tractor_254_ak"},
            {"name": "StuG III D Assault Gun", "sbps_id": "stug_iii_d_ak",
             "tier_upgrade_locked": True},
            {"name": "18-tonne Recovery Half-track", "sbps_id": "halftrack_recovery_ak",
             "tier_upgrade_locked": True},
        ],
        "t3": [
            {"name": "Panzer III L Medium Tank", "sbps_id": "panzer_iii_50mm_long_ak"},
            {"name": "Flak 36 Anti-tank Gun Team", "sbps_id": "at_gun_88mm_mobile_ak"},
            {"name": "Walking Stuka Rocket Launcher", "sbps_id": "halftrack_251_stuka_ak"},
        ],
    },

    # =================================================================
    # British Forces
    # =================================================================
    "uk": {
        "t0": [
            {"name": "Vickers Machine Gun Team", "sbps_id": "hmg_vickers_uk"},
            {"name": "Royal Engineer Section", "sbps_id": "sapper_uk"},
        ],
        "t1": [
            {"name": "Infantry Section", "sbps_id": "tommy_uk"},
            {"name": "ML 3-inch Mortar Team", "sbps_id": "mortar_81mm_uk"},
            {"name": "Dingo Light Scout Car", "sbps_id": "dingo_uk"},
        ],
        "t2": [
            {"name": "Humber Armored Car", "sbps_id": "humber_uk"},
            {"name": "CMP 15cwt Truck", "sbps_id": "pheasant_halftrack_uk"},
            {"name": "6-pounder Anti-tank Gun Team", "sbps_id": "at_gun_6pdr_uk"},
            {"name": "M3 Stuart Light Tank", "sbps_id": "stuart_uk",
             "tier_upgrade_locked": True},
            {"name": "Bishop Self-propelled Artillery", "sbps_id": "bishop_uk",
             "tier_upgrade_locked": True},
        ],
        "t4": [
            {"name": "Foot Guards Section", "sbps_id": "guards_uk"},
            {"name": "Matilda II Heavy Tank", "sbps_id": "matilda_uk"},
            {"name": "Crusader II Medium Tank", "sbps_id": "crusader_uk"},
            {"name": "17-pounder Anti-tank Gun Team", "sbps_id": "at_gun_17pdr_mobile_uk",
             "tier_upgrade_locked": True},
            {"name": "M3 Grant Medium Tank", "sbps_id": "grant_uk",
             "tier_upgrade_locked": True},
        ],
    },
}


# DAK has a special "T0 callin tree" - units callable from HQ via abilities,
# upgraded by a T4 ability into more powerful versions.
# These are NOT base production but appear in player builds and should be tracked.
DAK_CALLIN_TREE = {
    "base": [
        # Initial T0 callins (ability-based, not produced from buildings)
        "250 Assault Half-track w/ Assault Grens",
        "Towed Pak 38 callin",
        "Towed le.IG 18 callin",
        "Panzerjäger callin",
    ],
    "t4_upgraded": [
        # After T4 upgrade, these replace/add to the base callins
        "Panzer III + Engineer callin",
        "Double StuG III G callin",
        "Panzer IV + Assault Gren callin",
        "Tiger Heavy Tank callin",
    ],
}


def get_all_canonical_names() -> set[str]:
    """Return all unique unit names across all factions and tiers."""
    names = set()
    for fac_data in CANONICAL_BASE.values():
        for tier_units in fac_data.values():
            for u in tier_units:
                names.add(u["name"])
    return names


def get_all_canonical_sbps() -> set[str]:
    """Return all sbps_ids referenced in the canonical roster."""
    ids = set()
    for fac_data in CANONICAL_BASE.values():
        for tier_units in fac_data.values():
            for u in tier_units:
                ids.add(u["sbps_id"])
    return ids


def lookup_unit(faction: str, name: str) -> dict | None:
    """Find a unit's tier info by faction and name."""
    fac_data = CANONICAL_BASE.get(faction, {})
    for tier, units in fac_data.items():
        for u in units:
            if u["name"] == name:
                return {**u, "tier": tier, "faction": faction}
    return None
