"""
Generate unit_names.py - the canonical set of unit names from game data,
used by classify_action() to distinguish production from abilities.
"""

import json
from pathlib import Path

GAME_DATA = Path(__file__).parent / "game_data"
OUTPUT = Path(__file__).parent / "unit_names.py"


# Manual aliases - cohdb name -> game data name
# Add new entries here when name normalization fails to match
ALIASES = {
    "Sturmpioneer Squad": "Sturmpioneers",
    "2-pounder Anti-tank Gun Team": "2-pounder Light Anti-tank Gun Team",
    "Towed Cannone da 105/28 Field Howitzer": "Cannone da 105/28 Howitzer",
    "Towed ML 4.2-inch Heavy Mortar": "ML 4.2-inch Heavy Mortar Team",
    "Borgward IV Wanze Demolition Vehicle": "Borgward IV Wanze",
    "Command Panzer IV F Medium Tank": "Command Panzer IV Medium Tank",
}


INTERNAL_NAMES = {"sp", "specialist", "specialists", "parent_pbg",
                  "mass_production", "infantry_assault"}

# sbps_ids that LOOK like units in the game data but are actually:
# - Upgrade variants of existing units (M2HB .50cal is M1919 upgrade)
# - Not in multiplayer (WC54 Ambulance, Marksmen Team, Medic squads, UK Sniper)
# - Doctrine ability conversions (Assault Carriers upgrades M3 APC)
SKIP_SBPS = {
    # USF
    "hmg_50cal_us",            # M2HB .50cal - upgrade for M1919 via Heavy Weapons BG
    "ambulance_us",            # WC54 Ambulance - not in multiplayer
    "halftrack_assault_us",    # M3 Assault Carrier - upgrade for M3 APC via Heavy Weapons BG
    "marksman_team_partisan",  # Marksmen Team - not in multiplayer
    "medic_us",                # Medic - tied to healing structure, not a buildable squad
    "medic_partisan",          # Medic - same
    # Wehr
    "medic_ger",               # Medic - tied to medical bunker
    # DAK
    "medic_ak",                # Medic
    # UK - sniper does not exist for British forces, plus medic
    "sniper_uk",               # No British sniper in game
    "sniper_africa_uk",        # No British sniper
    "medic_uk",                # Medic
    "medic_africa_uk",         # Medic
    # Commandos and variants are NOT UK base roster - all doctrinal
    "commando_uk", "commando_africa_uk",
    "commando_lmg_uk", "commando_lmg_africa_uk",
    "hmg_commando_uk", "hmg_commando_africa_uk",
    "sas_squad_uk", "sas_africa_uk",
    "ssb_commando",
    # Other doctrinal-only UK units that the parser may show in base
    # NOTE: Foot Guards (guards_uk) IS UK T4 base - keep it!
    "australian_light_infantry_uk",                        # Aus Light Inf - DLC/dual
    "canadian_heavy_infantry_uk",                          # Canadian Shock - dual
    "gurkhas_uk",                                          # Gurkhas - dual
    # Stummel halftrack is an UPGRADE for 251 carrier, not a separate unit
    "halftrack_stummel_ger",
    "halftrack_stummel_recrewable_ger",
    "armored_car_8_rad_stummel_ak",  # DAK 8 Rad stummel - also an upgrade variant
}


def is_internal(name: str, sbps_id: str) -> bool:
    """Filter out internal/non-playable entries."""
    if sbps_id in SKIP_SBPS:
        return True
    if name in INTERNAL_NAMES:
        return True
    if name.islower() and "_" in name:
        return True
    if sbps_id.endswith("_sp") or "_sp_" in sbps_id:
        return True
    if sbps_id in INTERNAL_NAMES:
        return True
    if "mass_production" in sbps_id:
        return True
    if "_loiter_" in sbps_id or "_recon_" in sbps_id:
        # Aircraft loiter entries, not playable squads
        return True
    if sbps_id.startswith("partisan_tunnel"):
        return True
    return False


def main():
    with open(GAME_DATA / "unit_db.json") as f:
        db = json.load(f)

    names = set()
    for s in db["squads"]:
        if is_internal(s["name"], s["sbps_id"]):
            continue
        names.add(s["name"])

    # Add buildings from ebps
    buildings_path = GAME_DATA / "buildings.json"
    if buildings_path.exists():
        with open(buildings_path) as f:
            buildings = json.load(f)
        for b in buildings:
            if b and not b.islower() and b != "MISSING TEXT":
                names.add(b)

    # Add aliases as valid too (so the name as it appears in cohdb matches)
    for cohdb_name in ALIASES:
        names.add(cohdb_name)

    # Add (FACTION) suffixed forms for shared names that get disambiguated at load time
    # Source of truth: canonical_roster.AMBIGUOUS_SHARED_NAMES
    from canonical_roster import AMBIGUOUS_SHARED_NAMES as _ambig
    # We don't know per-name which factions to suffix here, so add all 4 - the
    # extras don't hurt (they just won't be used by load_build_orders_df).
    for base_name in _ambig:
        for fac in ("US", "WEHR", "UK", "DAK"):
            names.add(f"{base_name} ({fac})")

    sorted_names = sorted(names)

    out = [
        '"""',
        'AUTO-GENERATED canonical unit name set from game_data/unit_db.json.',
        'Used by classify_action() to identify production units vs abilities.',
        'Regenerate by running: python3 build_classifier_data.py',
        '"""',
        '',
        '# Set of all known unit names (production-able squads)',
        'UNIT_NAMES = {',
    ]
    for n in sorted_names:
        out.append(f'    {n!r},')
    out.append('}')
    out.append('')
    out.append('# Aliases: cohdb name -> game data name')
    out.append('UNIT_ALIASES = {')
    for k, v in sorted(ALIASES.items()):
        out.append(f'    {k!r}: {v!r},')
    out.append('}')
    out.append('')
    out.append('')
    out.append('def is_unit(name: str) -> bool:')
    out.append('    """Check if a name refers to a producible unit."""')
    out.append('    return name in UNIT_NAMES or name in UNIT_ALIASES')
    out.append('')
    out.append('')
    out.append('def canonicalize(name: str) -> str:')
    out.append('    """Return the canonical game-data name for a cohdb unit name."""')
    out.append('    return UNIT_ALIASES.get(name, name)')

    OUTPUT.write_text("\n".join(out) + "\n")
    print(f"Wrote {OUTPUT} with {len(sorted_names)} unit names + {len(ALIASES)} aliases")


if __name__ == "__main__":
    main()
