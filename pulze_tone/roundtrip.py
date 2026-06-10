"""
regression.py — prove the extracted writer still matches verified outputs.

Strategy per file:
  1. Decode the verified .prst to inspect body
  2. Work backward through amps.json to recover AMP knob labels + values
  3. Recover non-AMP slot modules (reverb, cab) from UID + chunk
  4. Recover chain_order from algoSlot, auto_cab flag from CAB UID
  5. Call build_preset() with the reconstructed recipe
  6. Byte-diff vs. the original file
"""
import json
import urllib.parse
from pathlib import Path

from .decoder import decode_prst, slot_chunk
from .writer import (
    build_preset, SLOT_NAMES, AMPS_BY_NAME, AUTO_CAB_UID,
    FACTORY_DEFAULT_UID, FACTORY_DEFAULT_CHUNK,
    _REVERBS_BY_NAME, _CABS_BY_NAME, _DELAYS_BY_NAME, _MODS_BY_NAME,
    _DIRTS_BY_NAME, _DYNS_BY_NAME, _EFFECTS_BY_SLOT_AND_NAME,
    _extract_enum_labels, _DUAL_PAIRS_BY_EFFECT_UID,
)

# Lazy-loaded div_enum_11 domain for reconstructing Sync=On delay Time values.
# Imported from the catalog once.
import json as _json
_CATALOG_FOR_DIV = _json.load(open(
    Path(__file__).parent / "data" / "EFFECT_CATALOG_v1.json"
))
_DIV_ENUM_11 = _CATALOG_FOR_DIV["shared_encodings"]["div_enum_11"]["domain"]

VERIFIED_DIR = Path(__file__).parent.parent / "tests" / "fixtures"

# UID → amp name map (built from AMPS_BY_NAME inverse)
AMPS_BY_UID = {int(a["uid"], 16): a for a in AMPS_BY_NAME.values()}
REVERBS_BY_UID = {int(e["uid"], 16): e for e in _REVERBS_BY_NAME.values()}
CABS_BY_UID = {int(e["uid"], 16): e for e in _CABS_BY_NAME.values()}
DELAYS_BY_UID = {int(e["uid"], 16): e for e in _DELAYS_BY_NAME.values()}
MODS_BY_UID = {int(e["uid"], 16): e for e in _MODS_BY_NAME.values()}
DIRTS_BY_UID = {int(e["uid"], 16): e for e in _DIRTS_BY_NAME.values()}
DYNS_BY_UID = {int(e["uid"], 16): e for e in _DYNS_BY_NAME.values()}
# EQ (cat 0x01 subcat=EQ) — shared pool at EQ/MOD slot only (7 effects)
EQS_BY_UID = {
    int(e["uid"], 16): e
    for e in _EFFECTS_BY_SLOT_AND_NAME.get("EQ/MOD", {}).values()
    if e.get("subcat") == "EQ"
}
# Filter (cat 0x01 subcat=Filter) — PRE slot (T-Wah G/B via v0.9 catalog patch;
# A-Wah/Pattern pending dual-encoding integration).
FILTERS_BY_UID = {
    int(e["uid"], 16): e
    for e in _EFFECTS_BY_SLOT_AND_NAME.get("PRE", {}).values()
    if e.get("cat") == "0x01" and e.get("subcat") == "Filter"
}
# Pitch (cat 0x01 subcat=Pitch) — PRE slot (Octa 1, Pitch, Detune, Octa 2, A-Harm
# via v0.10 catalog patch). All 5 share a common recovery path: no dual pairs,
# mix of continuous/toggle/enum/shared-clamp encodings all handled by _decode_knob.
PITCHES_BY_UID = {
    int(e["uid"], 16): e
    for e in _EFFECTS_BY_SLOT_AND_NAME.get("PRE", {}).values()
    if e.get("cat") == "0x01" and e.get("subcat") == "Pitch"
}
# Acoustic (cat 0x01 subcat=Acoustic) — PRE slot (AC Refiner, AC Sim via v0.11).
ACOUSTICS_BY_UID = {
    int(e["uid"], 16): e
    for e in _EFFECTS_BY_SLOT_AND_NAME.get("PRE", {}).values()
    if e.get("cat") == "0x01" and e.get("subcat") == "Acoustic"
}
# Special-A (cat 0x01 subcat=Special-A) — PRE slot (Bit Crush via v0.11).
SPECIAL_A_BY_UID = {
    int(e["uid"], 16): e
    for e in _EFFECTS_BY_SLOT_AND_NAME.get("PRE", {}).values()
    if e.get("cat") == "0x01" and e.get("subcat") == "Special-A"
}


def _recover_module_knobs(effect_entry, chunk, slot_id):
    """Walk param_chunk_positions and pull out any non-default values.
    Handles both absolute (cab) and slot-local (everything else) positions."""
    slot_base = slot_id * 15
    knobs = {}
    for label, raw_pos in effect_entry["param_chunk_positions"].items():
        local_pos = raw_pos - slot_base if raw_pos >= 15 else raw_pos
        v = chunk[local_pos]
        # Normalize to int if clean
        knobs[label] = int(v) if v == int(v) else v
    return knobs


def _decode_knob(raw_float, encoding_str):
    """Reverse the encoding: chunk float → recipe-ready value.

    Returns:
      - int for 1-indexed enum
      - string for 0-indexed enum with known labels (or int fallback)
      - int for continuous if clean-integer, else float

    Mirrors the dispatch in preset_writer._encode_knob.
    """
    import re as _re
    # 1-indexed integer enum
    if _re.match(r"1-INDEXED\s+rotary\s+enum:\s+integer\s+\d+-\d+", encoding_str):
        return int(raw_float)
    # 0-indexed integer enum — try label lookup
    if _re.match(r"rotary\s+enum:\s+integer\s+\d+-\d+", encoding_str):
        idx = int(raw_float)
        labels = _extract_enum_labels(encoding_str)
        for name, i in labels.items():
            if i == idx:
                return name
        return idx  # no label for this index — fall back to int
    # Continuous — emit int if clean, else float
    return int(raw_float) if raw_float == int(raw_float) else raw_float


def _recover_dual_knobs(effect_entry, chunk):
    """Reconstruct an effect's recipe knobs. Collapses every dual-encoded
    (Rate|Time)/(Sync) pair back into its recipe alias:
      - number for Sync=Off (ms or Hz)
      - string for Sync=On (div enum label)
    Non-dual knobs pass through _decode_knob (enum label lookup or
    continuous). Effects with zero dual pairs (Dimension, Sweller) fall
    straight to the knob loop."""
    positions = effect_entry["param_chunk_positions"]
    encodings = effect_entry["param_encodings"]
    pairs = _DUAL_PAIRS_BY_EFFECT_UID.get(effect_entry["uid"], [])

    knobs = {}
    skip = set()
    for pair in pairs:
        alias = pair["alias"]
        rate_pos = pair["rate_pos"]
        sync_pos = pair["sync_pos"]
        skip.add(pair["rate_key"])
        skip.add(pair["sync_key"])
        rate_raw = chunk[rate_pos]
        sync_val = chunk[sync_pos]
        if sync_val == 0.0:
            # Sync=Off → numeric (ms or Hz). Emit int when it's a clean
            # integer, else float — preserves user-friendly display of
            # 350 (delay) and 2.5 (Hz) alike.
            knobs[alias] = int(rate_raw) if rate_raw == int(rate_raw) else rate_raw
        elif sync_val == 1.0:
            idx = int(rate_raw)
            label = _DIV_ENUM_11.get(str(idx))
            if label is None:
                raise ValueError(
                    f"{effect_entry['name']}: div enum index {idx} out of 0-10 range"
                )
            knobs[alias] = label
        else:
            raise ValueError(
                f"{effect_entry['name']}: unexpected {pair['sync_key']} value "
                f"{sync_val} (expected 0.0 or 1.0)"
            )

    for label, raw_pos in positions.items():
        if label in skip:
            continue
        knobs[label] = _decode_knob(chunk[raw_pos], encodings.get(label, ""))
    return knobs


def recipe_from_prst(path: Path) -> dict:
    """Reconstruct the semantic recipe that would regenerate this preset."""
    header, body = decode_prst(path)

    name = urllib.parse.unquote(body["name"])
    chain_order = [SLOT_NAMES[i] for i in body["algoSlot"]]

    # AMP
    amp_uid = body["algoUID"][1]
    if amp_uid not in AMPS_BY_UID:
        raise ValueError(f"unknown amp UID 0x{amp_uid:08X} in {path.name}")
    amp = AMPS_BY_UID[amp_uid]
    amp_chunk = slot_chunk(body, 1)
    knobs = {}
    for label, spec in amp["knobs"].items():
        pos = spec["position"]
        actual = amp_chunk[pos]
        factory = amp["factory_chunk"][pos]
        if actual == factory:
            continue
        enc = spec["encoding"]
        if enc == "continuous_0_100":
            knobs[label] = int(actual) if actual == int(actual) else actual
        elif enc == "enum_0_indexed":
            idx = int(actual)
            opts = spec.get("options")
            knobs[label] = opts[idx] if opts and 0 <= idx < len(opts) else idx

    # CAB — three paths: auto-cab placeholder, named cab, or factory default
    cab_uid = body["algoUID"][3]
    auto_cab = cab_uid == AUTO_CAB_UID
    modules = {}

    if not auto_cab and cab_uid in CABS_BY_UID and cab_uid != FACTORY_DEFAULT_UID["CAB"]:
        # User explicitly named a cab other than the factory default
        cab_eff = CABS_BY_UID[cab_uid]
        cab_chunk = slot_chunk(body, 3)
        cab_knobs = {}
        cab_factory_chunk = FACTORY_DEFAULT_CHUNK["CAB"]
        for label, raw_pos in cab_eff["param_chunk_positions"].items():
            local_pos = raw_pos - 45 if raw_pos >= 15 else raw_pos
            v = cab_chunk[local_pos]
            fv = cab_factory_chunk[local_pos]
            if v != fv:
                cab_knobs[label] = int(v) if v == int(v) else v
        modules["CAB"] = {"effect": cab_eff["name"], "knobs": cab_knobs}

    # Decode enable bitmask once — used both to gate delay reconstruction
    # (disabled slots with factory-default content rebuild via the writer's
    # slot-factory fallback, not via an explicit module) and to emit the
    # authoritative enabled_slots field in the recipe.
    run_en = body["algoRunEn"]
    enabled_slots = [SLOT_NAMES[i] for i in range(7) if run_en & (1 << i)]

    # FX2 — reverb or delay based on UID. Only emit a module for an enabled
    # slot; a disabled FX2 with factory-default Digi Dly content rebuilds
    # correctly from the slot factory default without an explicit module.
    fx2_uid = body["algoUID"][6]
    fx2_enabled = bool(run_en & (1 << 6))
    if fx2_enabled and fx2_uid in REVERBS_BY_UID:
        rev = REVERBS_BY_UID[fx2_uid]
        fx2_chunk = slot_chunk(body, 6)
        rev_knobs = _recover_module_knobs(rev, fx2_chunk, 6)
        modules["FX2"] = {"effect": rev["name"], "knobs": rev_knobs}
    elif fx2_enabled and fx2_uid in DELAYS_BY_UID:
        delay = DELAYS_BY_UID[fx2_uid]
        fx2_chunk = slot_chunk(body, 6)
        modules["FX2"] = {
            "effect": delay["name"],
            "knobs": _recover_dual_knobs(delay, fx2_chunk),
        }

    # FX1 — delay or mod. Same enable gate.
    fx1_uid = body["algoUID"][5]
    fx1_enabled = bool(run_en & (1 << 5))
    if fx1_enabled and fx1_uid in DELAYS_BY_UID:
        delay = DELAYS_BY_UID[fx1_uid]
        fx1_chunk = slot_chunk(body, 5)
        modules["FX1"] = {
            "effect": delay["name"],
            "knobs": _recover_dual_knobs(delay, fx1_chunk),
        }
    elif fx1_enabled and fx1_uid in MODS_BY_UID:
        mod = MODS_BY_UID[fx1_uid]
        fx1_chunk = slot_chunk(body, 5)
        modules["FX1"] = {
            "effect": mod["name"],
            "knobs": _recover_dual_knobs(mod, fx1_chunk),
        }

    # PRE — mod, dirt, or Dynamic-subcat of cat 0x00 (Gate rejected per Guard #18).
    pre_uid = body["algoUID"][0]
    pre_enabled = bool(run_en & (1 << 0))
    if pre_enabled and pre_uid in MODS_BY_UID:
        mod = MODS_BY_UID[pre_uid]
        pre_chunk = slot_chunk(body, 0)
        modules["PRE"] = {
            "effect": mod["name"],
            "knobs": _recover_dual_knobs(mod, pre_chunk),
        }
    elif pre_enabled and pre_uid in DIRTS_BY_UID:
        dirt = DIRTS_BY_UID[pre_uid]
        pre_chunk = slot_chunk(body, 0)
        modules["PRE"] = {
            "effect": dirt["name"],
            "knobs": _recover_dual_knobs(dirt, pre_chunk),
        }
    elif pre_enabled and pre_uid in DYNS_BY_UID:
        dyn = DYNS_BY_UID[pre_uid]
        if dyn.get("subcat") == "Dynamic":
            pre_chunk = slot_chunk(body, 0)
            modules["PRE"] = {
                "effect": dyn["name"],
                "knobs": _recover_dual_knobs(dyn, pre_chunk),
            }
        # Gate in PRE is a device-side UI fallback case; recipe shouldn't
        # have produced this, but if it appears in a decoded preset we
        # silently drop it from the reconstructed recipe.
    elif pre_enabled and pre_uid in FILTERS_BY_UID:
        # Cat 0x01 Filter (T-Wah G/B via v0.9 schema patch). No dual pairs;
        # _recover_dual_knobs falls through to the knob loop and handles
        # the 4 continuous_0_100 knobs via _decode_knob.
        flt = FILTERS_BY_UID[pre_uid]
        pre_chunk = slot_chunk(body, 0)
        modules["PRE"] = {
            "effect": flt["name"],
            "knobs": _recover_dual_knobs(flt, pre_chunk),
        }
    elif pre_enabled and pre_uid in PITCHES_BY_UID:
        # Cat 0x01 Pitch (Octa 1, Pitch, Detune, Octa 2, A-Harm via v0.10
        # schema patch). No dual pairs; _recover_dual_knobs falls through
        # to the knob loop. _decode_knob handles continuous, signed
        # shared-clamp, toggle, and 0-indexed enums uniformly.
        pit = PITCHES_BY_UID[pre_uid]
        pre_chunk = slot_chunk(body, 0)
        modules["PRE"] = {
            "effect": pit["name"],
            "knobs": _recover_dual_knobs(pit, pre_chunk),
        }
    elif pre_enabled and pre_uid in ACOUSTICS_BY_UID:
        # Cat 0x01 Acoustic (AC Refiner, AC Sim via v0.11). No dual pairs.
        ac = ACOUSTICS_BY_UID[pre_uid]
        pre_chunk = slot_chunk(body, 0)
        modules["PRE"] = {
            "effect": ac["name"],
            "knobs": _recover_dual_knobs(ac, pre_chunk),
        }
    elif pre_enabled and pre_uid in SPECIAL_A_BY_UID:
        # Cat 0x01 Special-A (Bit Crush via v0.11). No dual pairs.
        sa = SPECIAL_A_BY_UID[pre_uid]
        pre_chunk = slot_chunk(body, 0)
        modules["PRE"] = {
            "effect": sa["name"],
            "knobs": _recover_dual_knobs(sa, pre_chunk),
        }

    # DYN — all 9 cat 0x00 effects (Dynamic + Gate).
    dyn_uid = body["algoUID"][2]
    dyn_enabled = bool(run_en & (1 << 2))
    if dyn_enabled and dyn_uid in DYNS_BY_UID:
        dyn_eff = DYNS_BY_UID[dyn_uid]
        dyn_chunk = slot_chunk(body, 2)
        modules["DYN"] = {
            "effect": dyn_eff["name"],
            "knobs": _recover_dual_knobs(dyn_eff, dyn_chunk),
        }

    # EQ/MOD — mod or EQ. EQ family added v0.8.
    eqmod_uid = body["algoUID"][4]
    eqmod_enabled = bool(run_en & (1 << 4))
    if eqmod_enabled and eqmod_uid in MODS_BY_UID:
        mod = MODS_BY_UID[eqmod_uid]
        eqmod_chunk = slot_chunk(body, 4)
        modules["EQ/MOD"] = {
            "effect": mod["name"],
            "knobs": _recover_dual_knobs(mod, eqmod_chunk),
        }
    elif eqmod_enabled and eqmod_uid in EQS_BY_UID:
        eq = EQS_BY_UID[eqmod_uid]
        eqmod_chunk = slot_chunk(body, 4)
        # EQ effects have no dual pairs; _recover_dual_knobs falls through
        # to the knob loop. That handles signed_dB_direct, Hz_direct,
        # Q_direct, continuous_0_100 uniformly via _decode_knob.
        modules["EQ/MOD"] = {
            "effect": eq["name"],
            "knobs": _recover_dual_knobs(eq, eqmod_chunk),
        }

    recipe = {
        "name": name,
        "amp": amp["name"],
        "auto_cab": auto_cab,
        "knobs": knobs,
        "chain_order": chain_order,
        "enabled_slots": enabled_slots,
        "bpm": body.get("bpm", 120),
        "volume": body.get("volume", 100),
        "id": body.get("ID", 1),
        "author": header.get("author", ""),
    }
    if modules:
        recipe["modules"] = modules
    return recipe


def run():
    files = sorted(VERIFIED_DIR.glob("*.prst"))
    results = []
    for path in files:
        original = path.read_bytes()
        try:
            recipe = recipe_from_prst(path)
            regenerated = build_preset(recipe)
        except Exception as e:
            results.append((path.name, False, f"exception: {e}", None))
            continue
        if regenerated == original:
            results.append((path.name, True, "byte-identical", recipe))
        else:
            n = min(len(original), len(regenerated))
            first_diff = next((i for i in range(n) if regenerated[i] != original[i]), -1)
            msg = f"DIFFER  orig={len(original)} new={len(regenerated)} first_diff={first_diff}"
            results.append((path.name, False, msg, recipe))

    print("=" * 72)
    print(f"REGRESSION: {len(files)} verified outputs (AMP + reverb + named-cab + delay + mod + dirt + dyn + cat 0x01 [EQ/Filter/Pitch/Acoustic/Special-A])")
    print("=" * 72)
    for name, ok, msg, _ in results:
        mark = "✓" if ok else "✗"
        print(f"  {mark}  {name:28s}  {msg}")
    passing = sum(1 for _, ok, _, _ in results if ok)
    print("=" * 72)
    print(f"PASS {passing}/{len(results)}")
    return results


if __name__ == "__main__":
    results = run()
    for name, ok, msg, recipe in results:
        if not ok:
            print(f"\n--- DEBUG {name} ---")
            print("reconstructed recipe:")
            print(json.dumps(recipe, indent=2, default=str))
            break

