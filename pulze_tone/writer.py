"""Pulze Mini Tone Generator — public fork (device-factory defaults).


preset_writer.py — Recipe → .prst bytes  (v0.11)

AMP layer (unchanged from v0.2):
  - continuous_0_100 knobs
  - enum_0_indexed knobs (pills + rotary_enums)
  - factory-default filling for unspecified knobs
  - gaps and engine_only positions (preserved at factory values)
  - chain reordering via semantic slot-name permutation

Module layer:
  - FX2 reverb (v0.3): 7 effects, continuous knobs, Pre Dly 0-300 ms
  - CAB (v0.4): 58 factory cabs, selectable via recipe['cab'] shorthand
    or modules.CAB. Catalog uses ABSOLUTE chunk positions for cabs
    (45-59 range), which are normalized to slot-local in the resolver.
  - Delay FX1/FX2 Sync=Off (v0.5): 11 delay effects, shared pool across
    FX1 and FX2. Time/Sync dual-encoding, Sync=Off branch only (number-
    type Time as ms float 20-2000). Sync=On (string-type Time as div
    enum index) deferred to v0.6. Encoding primitives added:
    signed_±100, unsigned 0-100, direct_percent (1.0-100.0).
  - Delay Sync=On (v0.7): string-type Time (e.g. "1/4", "1/8d") resolves
    via _DIV_ENUM_11_BY_LABEL (loaded from catalog shared_encodings).
    Writes integer 0-10 at Time/Div position, 1.0 at sync position.
    Actual milliseconds derived at playback time from preset-level bpm.
  - EQ family (v0.8): 7 cat 0x01 subcat=EQ effects, all EQ/MOD slot.
    Canonical-schema entries (no catalog patch needed). Adds two new
    continuous-range parse patterns: 'clamp ±N' (signed_dB_direct,
    symmetric), 'clamp A to B' (Hz_direct / Q_direct, verbal). No new
    _encode_knob branches — the continuous fallthrough handles them.
  - Filter family (v0.9): T-Wah G + T-Wah B (cat 0x01 subcat=Filter,
    PRE slot). First Shape B → canonical catalog patch. T-Wah B carries
    forward T-Wah G's layout via 'inherited_from' (provisional UID flagged
    in uid_status — scramble verification deferred as housekeeping).
  - Pitch family (v0.10): Octa 1, Pitch, Detune, Octa 2, A-Harm (cat 0x01
    subcat=Pitch, PRE slot). Second Shape B → canonical patch round.
    New encoding handlers: shared:signed_semitones_±24 and signed_cents_±50
    are expanded to self-describing clamp strings ('clamp A to B') that
    the existing continuous-range parser picks up. Dict-form enums
    (Key/Mode/Interval on A-Harm) are expanded to inline-label enum
    strings consumed by existing rotary-enum primitive. bool_toggle →
    canonical 'toggle 0.0=Off, 1.0=On'. engine_only positions lifted
    into engine_only_positions. 10 factory defaults pending pitch_fresh
    and octa2_fresh housekeeping; conservative 50.0 fills applied.
  - Acoustic + Special-A (v0.11): AC Refiner (1 UI knob + engine_only
    pos 1), AC Sim (3 unsigned_0_100 + 1 dict-enum Mode), Bit Crush
    (5 unsigned_0_100). Third Shape B → canonical patch round. No new
    _encode_knob branches needed — all primitives already in place.
    4 AC Sim factories pending acs_fresh housekeeping.

Module dispatch (v0.5 refactor):
  Unified _EFFECTS_BY_SLOT_AND_NAME index, built from catalog via
  _SUBCAT_ALLOWED_SLOTS. New families enabled by a single entry there.

Slot enable-state (v0.6):
  recipe['enabled_slots'] is authoritative when present — the runEn
  bitmask includes exactly those slots, nothing else. Allows any
  combination (all on, all off, an enabled slot with factory-default
  content, content-in-a-disabled-slot). When omitted, the pre-v0.6
  inference path runs (AMP always; CAB if auto_cab or modules.CAB;
  any slot in modules). Mutually exclusive with 'enabled_extra'.

Auto-cab behavior:
  - recipe['auto_cab'] = True       → writes placeholder UID 0x0A000000
                                      (device's NVRAM auto-cab decides at load)
  - recipe['cab'] = "<name>"        → writes the named cab's UID + knobs
                                      (deterministic; preferred for new recipes)
  - both absent                     → writes factory-default Gibby 1x10
  - modules.CAB.effect              → equivalent to recipe['cab'], explicit form
"""
import base64
import json
import re
import urllib.parse
from copy import deepcopy
from pathlib import Path


# ──────────────────────────────────────────────────────────────────────────
#  Slot identity
# ──────────────────────────────────────────────────────────────────────────
SLOT_NAMES = ["PRE", "AMP", "DYN", "CAB", "EQ/MOD", "FX1", "FX2"]
SLOT_IDX   = {n: i for i, n in enumerate(SLOT_NAMES)}
SLOT_BIT   = {n: 1 << i for i, n in enumerate(SLOT_NAMES)}


# ──────────────────────────────────────────────────────────────────────────
#  Empty-slot defaults, V1.1.0. Originally captured from gibby_all_low.prst
#  (an everything-dialed-low export — NOT factory defaults; source of the
#  v7.2-era CAB High Cut 2000-vs-20000 bug). v7.4: knob positions verified
#  against catalog per-knob factory defaults; engine-only stamps applied per
#  slot (PRE/Comp 1 pos2=60; EQ/MOD/GtrEQ1 pos10,14=50; FX1/Chorus pos5
#  correctly ABSENT — explicit empty fx1-slot stamp set). CAB is the Busket
#  base per §6.7: Low Cut 19.0 Off + High Cut 20000.0. AMP is always
#  overwritten by recipe["amp"] and never survives to output.
# ──────────────────────────────────────────────────────────────────────────
FACTORY_DEFAULT_UID = {
    "PRE":    0x00000000, "AMP":    0x07000001, "DYN":    0x0000001B,
    "CAB":    0x0A000075, "EQ/MOD": 0x01000035, "FX1":    0x0400000C,
    "FX2":    0x0B00001F,
}
FACTORY_DEFAULT_CHUNK = {
    "PRE":    [20.0, 50.0, 60.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],  # pos2=60 Comp 1 engine stamp (v7.4)
    "AMP":    [30.0, 50.0, 50.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "DYN":    [20.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,   0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "CAB":    [0.0, 50.0, 0.0, 0.0, 0.0, 80.0, 20001.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],  # device factory: Vol 50, Low Cut 80 Hz, High Cut Off (sentinel 20001)
    "EQ/MOD": [0.0, 0.0, 0.0, 0.0, 0.0, 50.0, 0.0, 0.0, 0.0, 0.0, 50.0, 0.0, 0.0, 0.0, 50.0],  # pos10,14=50 GtrEQ1 engine stamps (v7.4)
    "FX1":    [70.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0,   0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "FX2":    [20.0, 4.0, 20.0, 61.79999923706055, 100.0, 50.0, 1.0,
               0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
}

AUTO_CAB_UID = 0x0A000000


# ──────────────────────────────────────────────────────────────────────────
#  Public slot-name aliases (device-official terminology)
#    Sound Clone 1-10  →  catalog "NAM n"        (user NAM capture slots)
#    User IR 1-20      →  catalog "Custom IR n"  (user impulse-response slots)
#  Legacy names remain valid. Describe what YOU loaded per slot in
#  user_layer.json (informational; lets an AI assistant route by tone).
# ──────────────────────────────────────────────────────────────────────────
_SC_RE = re.compile(r"^\s*(?:sound\s*clone|sc|nam)\s*(\d{1,2})\s*$", re.IGNORECASE)
_IR_RE = re.compile(r"^\s*(?:user\s*ir|custom\s*ir|ir)\s*(\d{1,2})\s*$", re.IGNORECASE)

def canonical_amp_name(name):
    m = _SC_RE.match(str(name))
    return f"NAM {int(m.group(1))}" if m else name

def canonical_effect_name(name):
    m = _IR_RE.match(str(name))
    return f"Custom IR {int(m.group(1))}" if m else name



# ──────────────────────────────────────────────────────────────────────────
#  Load amps catalog
# ──────────────────────────────────────────────────────────────────────────
_DATA_DIR = Path(__file__).parent / "data"
with open(_DATA_DIR / "amps.json") as f:
    _AMPS_BY_UID = json.load(f)

AMPS_BY_NAME = {a["name"]: a for a in _AMPS_BY_UID.values()}


# ──────────────────────────────────────────────────────────────────────────
#  Load effect catalog (for module slots: PRE, DYN, CAB, EQ/MOD, FX1, FX2)
# ──────────────────────────────────────────────────────────────────────────
_CATALOG_PATH = _DATA_DIR / "EFFECT_CATALOG_v1.json"
with open(_CATALOG_PATH) as f:
    _EFFECT_CATALOG = json.load(f)

# Subcat → allowed slots (from SLOT_AND_CHAIN_RULES_v4_5_9.md §2)
# Only populated for subcats the writer currently handles; extend as families
# come online.
_SUBCAT_ALLOWED_SLOTS = {
    # EQ (cat 0x01) — 7 effects, all EQ/MOD slot (v0.8)
    ("0x01", "EQ"):         {"EQ/MOD"},
    # Filter (cat 0x01) — T-Wah G/B via Shape B→A patch, A-Wah/Pattern pending (v0.9)
    ("0x01", "Filter"):     {"PRE"},
    # Pitch (cat 0x01) — Octa 1, Pitch, Detune, Octa 2, A-Harm (v0.10)
    ("0x01", "Pitch"):      {"PRE"},
    # Acoustic (cat 0x01) — AC Refiner, AC Sim (v0.11)
    ("0x01", "Acoustic"):   {"PRE"},
    # Special-A (cat 0x01) — Bit Crush (v0.11)
    ("0x01", "Special-A"):  {"PRE"},
    # Reverb (cat 0x0C)
    ("0x0C", "Reverb"):     {"FX2"},
    # Delay (cat 0x0B)
    ("0x0B", "Delay"):      {"FX1", "FX2"},
    # Modulation + Special-B (cat 0x04)
    ("0x04", "Chorus"):     {"PRE", "EQ/MOD", "FX1"},
    ("0x04", "Flanger"):    {"PRE", "EQ/MOD", "FX1"},
    ("0x04", "Phaser"):     {"PRE", "EQ/MOD", "FX1"},
    ("0x04", "Rotary"):     {"PRE", "EQ/MOD", "FX1"},
    ("0x04", "Tremolo"):    {"PRE", "EQ/MOD", "FX1"},
    ("0x04", "Vibrato"):    {"PRE", "EQ/MOD", "FX1"},
    ("0x04", "Special-B"):  {"PRE", "EQ/MOD", "FX1"},
    # Dirt (cat 0x03) — Bass here means bass dirt, NOT bass cab
    ("0x03", "Overdrive"):  {"PRE"},
    ("0x03", "Distortion"): {"PRE"},
    ("0x03", "Fuzz"):       {"PRE"},
    ("0x03", "Bass"):       {"PRE"},
    # Dynamics + Gate (cat 0x00) — Gate is DYN-exclusive per family_spec;
    # loading Gate in PRE triggers device UI fallback to Comp 1 factory
    ("0x00", "Dynamic"):    {"DYN", "PRE"},
    ("0x00", "Gate"):       {"DYN"},
    # Cabs (cat 0x0A) — Bass here means bass cab
    ("0x0A", "Guitar S"):   {"CAB"},
    ("0x0A", "Guitar L"):   {"CAB"},
    ("0x0A", "Bass"):       {"CAB"},
    ("0x0A", "Celestion"):  {"CAB"},
    ("0x0A", "Acoustic"):   {"CAB"},
    ("0x0A", "User IR"):    {"CAB"},
}

# Index reverb effects by name. Unique within subcat per the catalog.
_REVERBS_BY_NAME = {
    e["name"]: e
    for e in _EFFECT_CATALOG["effects"]
    if e.get("subcat") == "Reverb"
}

# Index delay effects by name. Unique within subcat (cat 0x0B) per catalog.
# Delays are a shared pool across FX1 and FX2 — same UID in either slot.
_DELAYS_BY_NAME = {
    e["name"]: e
    for e in _EFFECT_CATALOG["effects"]
    if e.get("subcat") == "Delay"
}

# Index Mod + Special-B effects (cat 0x04) by name. Legal in PRE, EQ/MOD, FX1.
# Subcats: Chorus, Flanger, Phaser, Rotary, Tremolo, Vibrato, Special-B.
_MOD_SUBCATS = {"Chorus", "Flanger", "Phaser", "Rotary", "Tremolo", "Vibrato", "Special-B"}
_MODS_BY_NAME = {
    e["name"]: e
    for e in _EFFECT_CATALOG["effects"]
    if e.get("subcat") in _MOD_SUBCATS
}

# Index Dirt effects (cat 0x03) by name. Legal in PRE only.
# Subcats: Overdrive, Distortion, Fuzz, Bass (bass-dirt, NOT bass-cab).
# Disambiguated by category code — subcat 'Bass' collides with cab 0x0A.
_DIRTS_BY_NAME = {
    e["name"]: e
    for e in _EFFECT_CATALOG["effects"]
    if e.get("cat") == "0x03"
}

# Index Dynamics + Gate effects (cat 0x00) by name. Legal in DYN (all 9)
# and PRE (Dynamic subcat only — Gate in PRE triggers device UI fallback
# to Comp 1, so the writer rejects it per Guard #18).
_DYNS_BY_NAME = {
    e["name"]: e
    for e in _EFFECT_CATALOG["effects"]
    if e.get("cat") == "0x00"
}

# Index cabs by name. Names are unique within cat 0x0A per catalog audit.
# Filter on BOTH cat and subcat because 'Bass' subcat appears in cat 0x03
# (bass dirt) too.
_CAB_SUBCATS = {"Guitar S", "Guitar L", "Bass", "Celestion", "Acoustic", "User IR"}
_CABS_BY_NAME = {
    e["name"]: e
    for e in _EFFECT_CATALOG["effects"]
    if e.get("cat") == "0x0A" and e.get("subcat") in _CAB_SUBCATS
}

# Unified slot-keyed index. Built from the catalog by filtering each effect's
# subcat through _SUBCAT_ALLOWED_SLOTS. For every (slot, name) pair the user
# might ask for, this resolves directly to the catalog entry. New families are
# enabled by adding their subcat → slot mapping in _SUBCAT_ALLOWED_SLOTS above;
# no changes needed here.
_EFFECTS_BY_SLOT_AND_NAME = {}
for _e in _EFFECT_CATALOG["effects"]:
    for _slot in _SUBCAT_ALLOWED_SLOTS.get((_e.get("cat"), _e.get("subcat")), set()):
        _EFFECTS_BY_SLOT_AND_NAME.setdefault(_slot, {})[_e["name"]] = _e
del _e, _slot

# Shared tempo-division enum (used by Delay Sync=On; Mod Sync=On will reuse).
# Maps user-facing label like "1/4" → integer chunk value 0-10. Loaded from
# catalog's shared_encodings.div_enum_11 so writer and reconstructor can't drift.
_DIV_ENUM_11_BY_LABEL = {
    label: int(idx)
    for idx, label in _EFFECT_CATALOG["shared_encodings"]["div_enum_11"]["domain"].items()
}

# Recipe-alias → catalog-key mapping for dual-encoded pairs. The user-facing
# alias in the recipe differs from the internal catalog position key so that
# (a) the Sync byte stays inferred rather than explicit and (b) the Rate/Time
# naming matches the recipe-writer convention. Rotary is the only effect
# with two independent pairs.
_DUAL_PAIR_ALIAS_MAP = {
    "Time/Div":    ("Time",    "Sync"),
    "Rate/Div":    ("Rate",    "Sync"),
    "B. Rate/Div": ("B. Rate", "Bass Sync"),
    "H. Rate/Div": ("H. Rate", "Horn Sync"),
}

def _build_dual_pairs(effect):
    """Return a list of dual-encoded pair metadata dicts for this effect.
    Each pair: {alias, rate_key, sync_key, rate_pos, sync_pos, encoding}.
    Most effects have 0 or 1 pair; Rotary has 2. Scanning is driven by the
    'DUAL encoding' marker in each knob's encoding string — so adding a new
    effect to the catalog with a DUAL-encoded knob automatically gets the
    gate without writer code changes, provided the alias map covers it."""
    positions = effect.get("param_chunk_positions", {})
    encodings = effect.get("param_encodings", {})
    pairs = []
    for rate_key, enc in encodings.items():
        if "DUAL encoding" not in enc:
            continue
        if rate_key not in _DUAL_PAIR_ALIAS_MAP:
            raise ValueError(
                f"{effect.get('name')}: dual-encoded catalog key {rate_key!r} "
                f"has no alias mapping in _DUAL_PAIR_ALIAS_MAP"
            )
        alias, sync_key = _DUAL_PAIR_ALIAS_MAP[rate_key]
        if sync_key not in positions:
            raise ValueError(
                f"{effect.get('name')}: dual-encoded {rate_key!r} has no "
                f"matching {sync_key!r} in param_chunk_positions"
            )
        pairs.append({
            "alias":    alias,
            "rate_key": rate_key,
            "sync_key": sync_key,
            "rate_pos": positions[rate_key],
            "sync_pos": positions[sync_key],
            "encoding": enc,
        })
    return pairs

_DUAL_PAIRS_BY_EFFECT_UID = {
    e["uid"]: _build_dual_pairs(e)
    for e in _EFFECT_CATALOG["effects"]
}


def _parse_dual_range(encoding_str):
    """Extract (lo, hi) from a DUAL encoding's 'clamp A-B' marker.

    Every DUAL-encoded knob documents its Sync=0 numeric range explicitly
    (e.g. 'ms float clamp 20.0-2000.0' for delay, 'Hz float clamp 0.10-10.00'
    for standard mod, 'Hz float clamp 0.10-16.00' for Rotary). Raises on
    miss — a catalog-malformed DUAL encoding is a bug, not a fallback case.
    """
    m = re.search(r"clamp\s+(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)", encoding_str)
    if m:
        return float(m.group(1)), float(m.group(2))
    raise ValueError(
        f"DUAL encoding missing 'clamp A-B' marker: {encoding_str[:100]}"
    )


def _parse_continuous_range(encoding_str):
    """Infer (lo, hi) clamp bounds from an encoding string.

    Returns (0.0, 100.0) fallback for anything that doesn't match a known
    pattern. Recognized encodings (delay family expanded v0.5, EQ added v0.8):
      - 'continuous A-B ...'                       → (A, B)
      - 'signed_±100 direct'                        → (-100.0, 100.0)
      - 'unsigned 0-100 direct'                     → (0.0, 100.0)
      - '... float A-B ...' (direct_percent, etc.)  → (A, B)
      - 'clamp A-B ...'                             → (A, B)
      - 'clamp ±N ...'          (signed_dB_direct)  → (-N, N)
      - 'clamp A to B'          (Hz_direct/Q_direct) → (A, B)
      - 'direct Hz (valid range A-B)' (cab Low/High Cut) → (A, B)

    Non-continuous encodings (DUAL, enum, 1-indexed enum, toggle) are NOT
    handled here — callers must branch on them before reaching this.

    Note on cab Hz sentinels (Low Cut <20 displays 'Off'; High Cut >20000
    displays 'Off'): the clamp range is the *valid audible* range, so a
    user value like 500 Hz Low Cut stores as 500.0 (correct). To keep a
    cut knob Off, OMIT the knob from the recipe — the factory-default
    chunk carries the sentinel through. Recipes should not pass
    0 or a string; the knob must be omitted for Off.
    """
    # 'continuous A-B ...'
    m = re.search(r"continuous\s+(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)", encoding_str)
    if m:
        return float(m.group(1)), float(m.group(2))
    # Signed ±100 (FB on 7 delays, Spread on 5 delays, Direction on Icy Dly)
    if "signed_±100" in encoding_str:
        return -100.0, 100.0
    # Explicit unsigned 0-100 (FB on 4 delays — same range as fallback but named)
    if "unsigned 0-100" in encoding_str:
        return 0.0, 100.0
    # 'float A-B' inside longer encodings (e.g. direct_percent Time R% → 1.0-100.0)
    m = re.search(r"float\s+(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)", encoding_str)
    if m:
        return float(m.group(1)), float(m.group(2))
    # 'clamp A-B' — generic clamp marker (Sweller Attack: "continuous ms float direct, clamp 80-4000 ms")
    m = re.search(r"clamp\s+(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)", encoding_str)
    if m:
        return float(m.group(1)), float(m.group(2))
    # 'clamp ±N' — symmetric clamp (EQ family: signed_dB_direct bands)
    # Matches 'clamp ±50 dB', 'clamp ±12 dB'. Returns (-N, +N).
    m = re.search(r"clamp\s+±\s*(\d+(?:\.\d+)?)", encoding_str)
    if m:
        n = float(m.group(1))
        return -n, n
    # 'clamp A to B' — verbal clamp (Para EQ: 'clamp 20 Hz to 2000 Hz',
    # 'clamp 0.10 to 10.00'). Tolerates an optional unit between A and 'to'.
    m = re.search(
        r"clamp\s+(-?\d+(?:\.\d+)?)(?:\s*[A-Za-z]+)?\s+to\s+(-?\d+(?:\.\d+)?)",
        encoding_str,
    )
    if m:
        return float(m.group(1)), float(m.group(2))
    # 'direct Hz (valid range A-B)' — cab Low Cut / High Cut (v6.1 addition).
    # Matches every cab's Low Cut (20-2000) and High Cut (2000-20000). Off
    # sentinels (<20 for Low Cut, >20000 for High Cut) are reached only by
    # OMITTING the knob — the factory-default chunk carries the sentinel.
    m = re.search(
        r"valid\s+range\s+(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)",
        encoding_str,
    )
    if m:
        return float(m.group(1)), float(m.group(2))
    return 0.0, 100.0


def _extract_enum_labels(encoding_str):
    """Return {label_string: int_index} for enum encoding strings.

    Priority:
      1. 'see shared_encodings.<name>' reference → load domain from catalog
      2. Inline 'N=Name' pairs (strict — no whitespace around '=', so
         editorial notes like 'idx 14 = unison' are NOT matched).
    Returns empty dict for integer-only enums (Multi Tap Mode).
    """
    # Shared-encodings reference (e.g. 'see shared_encodings.pitch_enum_31')
    m = re.search(r"shared_encodings\.(\w+)", encoding_str)
    if m:
        ref = _EFFECT_CATALOG["shared_encodings"].get(m.group(1))
        if ref and "domain" in ref:
            return {label: int(idx_str) for idx_str, label in ref["domain"].items()}
    # Inline 'N=Label' pairs via slice-between-markers. Label extends from
    # the char after '=' up to the next 'N=' marker or end of string.
    # Trailing ','/';' stripped; a FINAL unbalanced ')' is stripped so that
    # 'integer 0-2 (0=Slow, 1=Medium, 2=Fast)' yields label 'Fast' rather
    # than 'Fast)'. Balanced parens INSIDE a label are preserved (e.g.
    # 'I (asymm)' for T-Mee Mode). Negative lookbehind (?<!\\.) guards
    # against toggle strings like '0.0=Off'.
    pairs = list(re.finditer(r"(?<!\.)(\d+)=", encoding_str))
    labels = {}
    for i, pm in enumerate(pairs):
        idx = int(pm.group(1))
        start = pm.end()
        end = pairs[i + 1].start() if i + 1 < len(pairs) else len(encoding_str)
        raw = encoding_str[start:end].strip().rstrip(",;").rstrip()
        while raw.endswith(')') and raw.count('(') < raw.count(')'):
            raw = raw[:-1].rstrip()
        if raw:
            labels[raw] = idx
    return labels


def _encode_knob(value, encoding_str, label, effect_name):
    """Encode a user knob value to the float32 chunk value per its encoding.

    Dispatch order:
      1. Toggle (dirt Fat/Air/Drive): 'toggle 0.0=Off, 1.0=On' — accepts
         bool, 'On'/'Off' (case-insensitive), or 0/1.
      2. 1-indexed integer enum (Multi Tap Mode): int only, saturation clamp.
      3. 0-indexed integer enum with explicit 'integer N-M' range
         (Icy Pitch/Slice): string label lookup or int.
      4. 0-indexed enum with inline labels only (Bass OD3 Attack, T-Mee Mode):
         range inferred from label indices; string label lookup or int.
      5. Continuous + range clamp (everything else — falls through to
         _parse_continuous_range).

    Returns the float to write into the chunk.
    """
    # Toggle — accepts both 'toggle 0.0=Off, 1.0=On' (dirt-style, e.g. TS Drv+
    # Fat/Air) and 'toggle: 0.0=Off, 1.0=On' (dyn-style, e.g. Boost 3 Low Cut).
    if re.match(r"toggle:?\s+0\.0=Off,\s*1\.0=On", encoding_str):
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        if isinstance(value, str):
            v = value.strip().lower()
            if v == "on":
                return 1.0
            if v == "off":
                return 0.0
            raise ValueError(
                f"{effect_name}.{label}: toggle accepts bool / 'On' / 'Off' / 0 / 1, "
                f"got {value!r}"
            )
        if isinstance(value, (int, float)):
            iv = int(value)
            if iv in (0, 1) and float(value) == float(iv):
                return float(iv)
            raise ValueError(
                f"{effect_name}.{label}: toggle accepts 0 or 1, got {value}"
            )
        raise ValueError(
            f"{effect_name}.{label}: toggle accepts bool/string/0/1, "
            f"got {type(value).__name__}"
        )

    # 1-indexed integer enum — no labels supported yet
    m = re.match(r"1-INDEXED\s+rotary\s+enum:\s+integer\s+(\d+)-(\d+)", encoding_str)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        if isinstance(value, bool):
            raise ValueError(f"{effect_name}.{label}: bool not accepted for integer enum")
        if isinstance(value, str):
            raise ValueError(
                f"{effect_name}.{label}: 1-indexed integer enum (valid {lo}-{hi}); "
                f"pass integer, got {value!r}. Symbolic labels not enumerated yet."
            )
        v = int(value)
        if v < lo:
            v = lo
        elif v > hi:
            v = hi
        return float(v)

    # 0-indexed integer enum with explicit range — may accept labels or integers
    m = re.match(r"rotary\s+enum:\s+integer\s+(\d+)-(\d+)", encoding_str)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        labels = _extract_enum_labels(encoding_str)
        if isinstance(value, bool):
            raise ValueError(f"{effect_name}.{label}: bool not accepted for enum")
        if isinstance(value, str):
            if value in labels:
                idx = labels[value]
                if not (lo <= idx <= hi):
                    raise ValueError(
                        f"{effect_name}.{label}={value!r} resolves to idx {idx} "
                        f"out of integer range [{lo}, {hi}]"
                    )
                return float(idx)
            raise ValueError(
                f"{effect_name}.{label}={value!r}: unknown enum label. "
                f"Valid labels: {sorted(labels) if labels else '(none — use integer)'}. "
                f"Valid integers: {lo}-{hi}."
            )
        v = int(value)
        if v < lo or v > hi:
            raise ValueError(
                f"{effect_name}.{label} value {value} out of integer range [{lo}, {hi}]"
            )
        return float(v)

    # 0-indexed enum with inline labels only — range inferred from label indices
    # (Bass OD3 Attack: 'rotary enum: 0=CUT, 1=BOOST, 2=FLAT';
    #  T-Mee Mode: 'rotary enum: 0=I (asymm), 1=II (symm), 2=III (symm+comp)')
    if re.match(r"rotary\s+enum:\s+\d+=", encoding_str):
        labels = _extract_enum_labels(encoding_str)
        if not labels:
            raise ValueError(
                f"{effect_name}.{label}: encoding parses as inline-label enum "
                f"but no labels extracted: {encoding_str[:80]}"
            )
        lo, hi = min(labels.values()), max(labels.values())
        if isinstance(value, bool):
            raise ValueError(f"{effect_name}.{label}: bool not accepted for enum")
        if isinstance(value, str):
            if value in labels:
                return float(labels[value])
            raise ValueError(
                f"{effect_name}.{label}={value!r}: unknown enum label. "
                f"Valid labels: {sorted(labels)}. Valid integers: {lo}-{hi}."
            )
        v = int(value)
        if v < lo or v > hi:
            raise ValueError(
                f"{effect_name}.{label} value {value} out of integer range [{lo}, {hi}]"
            )
        return float(v)

    # Off-sentinel branch (cab Low Cut / High Cut and any future param whose
    # encoding declares an out-of-range Off sentinel, e.g.
    # "valid range 2000-20000; chunk value >20000 displays 'Off' (sentinel 20001.0)").
    # Accepts the literal string 'Off' or the exact sentinel number. Without
    # this branch the sentinel is unreachable from recipes because it sits
    # outside the continuous clamp range. Doctrine §6.7 mandates 20000.0 for
    # Busket recipes but explicitly allows the 20001.0 sentinel for
    # Layer-0-OFF recipes; the writer must be able to express both.
    m = re.search(r"sentinel\s+(\d+(?:\.\d+)?)", encoding_str)
    if m:
        sentinel = float(m.group(1))
        if isinstance(value, str) and value.strip().lower() == "off":
            return sentinel
        if isinstance(value, (int, float)) and not isinstance(value, bool) \
                and float(value) == sentinel:
            return sentinel

    # Continuous fallback
    lo, hi = _parse_continuous_range(encoding_str)
    if isinstance(value, bool):
        raise ValueError(f"{effect_name}.{label}: bool not accepted for continuous knob")
    v = float(value)
    if v < lo or v > hi:
        raise ValueError(
            f"{effect_name}.{label} value {value} out of [{lo}, {hi}]"
        )
    return v


def _engine_only_for_slot(effect_entry, slot_name):
    """Return the engine_only_positions dict for a given slot, or {}.

    Catalog keys are e.g. 'engine_only_positions_fx2_slot'. Slot-specific
    fields override the generic 'engine_only_positions' even when empty —
    an explicit `{}` at the slot level means "no stamps in this slot,"
    which must NOT fall through to the generic list (see Chorus: pos 5=50
    in EQ/MOD but no stamp in FX1, where the generic field happens to be
    non-empty for backwards compat)."""
    key = f"engine_only_positions_{slot_name.lower().replace('/', '_')}_slot"
    if key in effect_entry:
        val = effect_entry[key] or {}
        return {int(k): float(v) for k, v in val.items()}
    val = effect_entry.get("engine_only_positions")
    if val:
        return {int(k): float(v) for k, v in val.items()}
    return {}


def _resolve_module(slot_name, module_spec):
    """Resolve a (slot, {effect, knobs}) spec to (uid, 15-float chunk).

    Dispatch: unified lookup via _EFFECTS_BY_SLOT_AND_NAME. A family is
    supported once its subcat is registered in _SUBCAT_ALLOWED_SLOTS.
    The resolver body below is family-agnostic; per-subcat policies
    (starting chunk, encoding parsing) branch from the resolved entry.
    """
    effect_name = canonical_effect_name(module_spec["effect"])

    slot_index = _EFFECTS_BY_SLOT_AND_NAME.get(slot_name, {})
    if effect_name not in slot_index:
        if not slot_index:
            raise NotImplementedError(
                f"module slot {slot_name!r} has no supported effect families "
                f"yet (register a subcat in _SUBCAT_ALLOWED_SLOTS to enable)"
            )
        raise ValueError(
            f"unknown effect {effect_name!r} for slot {slot_name}. "
            f"Available: {sorted(slot_index)}"
        )
    eff = slot_index[effect_name]

    # Legality gate — defensive double-check. The slot-keyed index already
    # enforced legality during construction; this catches any drift between
    # catalog subcats and _SUBCAT_ALLOWED_SLOTS.
    allowed = _SUBCAT_ALLOWED_SLOTS.get((eff.get("cat"), eff["subcat"]), set())
    if slot_name not in allowed:
        raise ValueError(
            f"{eff['subcat']} effect {effect_name!r} cannot go in {slot_name} "
            f"(allowed: {sorted(allowed)})"
        )

    uid = int(eff["uid"], 16)
    slot_id = SLOT_IDX[slot_name]
    slot_base = slot_id * 15  # for converting absolute → local positions

    # Per-subcat starting-chunk policy. CAB effects start from the Busket CAB
    # base chunk: Low Cut 19.0 (Off sentinel) + High Cut 20000.0 (active 20 kHz
    # ceiling per doctrine §6.7 — NOT the 20001.0 factory Off sentinel, and NOT
    # 2000.0 which is the High Cut FLOOR / maximum filtering, a historical bug
    # fixed in v7.3). Every other family starts from zeros plus
    # any engine-only positions the catalog specifies for this slot. Note
    # we gate on cat+subcat because 'Bass' collides between cab (cat 0x0A)
    # and bass-dirt (cat 0x03) — dirt must not start from the CAB chunk.
    if eff.get("cat") == "0x0A" and eff["subcat"] in _CAB_SUBCATS:
        chunk = deepcopy(FACTORY_DEFAULT_CHUNK["CAB"])
    else:
        chunk = [0.0] * 15
        for pos, val in _engine_only_for_slot(eff, slot_name).items():
            chunk[pos] = val

    positions = eff["param_chunk_positions"]
    encodings = eff["param_encodings"]
    user_knobs = dict(module_spec.get("knobs", {}))

    # ──────────────────────────────────────────────────────────────────
    #  Dual-encoding gate — catalog-driven. Each effect's pairs are
    #  precomputed in _DUAL_PAIRS_BY_EFFECT_UID; most effects have 0 or 1
    #  pair, Rotary has 2 (Bass/Horn rotors, independent sync each).
    #
    #  Recipe contract per pair:
    #    - User passes a single alias (Time / Rate / B. Rate / H. Rate).
    #    - Value type picks the Sync-off vs Sync-on branch:
    #        number  → Sync=Off, write as float in [lo, hi] from encoding
    #        string  → Sync=On,  lookup in div_enum_11, write int 0-10
    #    - The internal catalog keys (Time/Div, Rate/Div, Sync, Bass Sync,
    #      Horn Sync) are forbidden in recipes — they're set by the gate.
    #    - The alias is REQUIRED when the effect has any dual-encoded
    #      pair. No implicit defaulting. If user wants factory behavior,
    #      they should leave the module unset entirely.
    # ──────────────────────────────────────────────────────────────────
    pairs = _DUAL_PAIRS_BY_EFFECT_UID.get(eff["uid"], [])
    for pair in pairs:
        alias = pair["alias"]
        rate_key = pair["rate_key"]
        sync_key = pair["sync_key"]
        # Forbid the raw catalog names in user_knobs
        for forbidden in (rate_key, sync_key):
            if forbidden in user_knobs:
                raise ValueError(
                    f"do not pass {forbidden!r} in recipe knobs — "
                    f"use {alias!r} (number for ms/Hz Sync=Off, string like "
                    f"'1/4' for Sync=On); the writer sets the sync byte "
                    f"internally"
                )
        if alias not in user_knobs:
            lo, hi = _parse_dual_range(pair["encoding"])
            raise ValueError(
                f"{effect_name} requires {alias!r} in knobs. "
                f"Pass a number (Sync=Off range {lo}-{hi}) or a division "
                f"string (e.g. '1/4', Sync=On). No implicit default is "
                f"supplied — leave the module unset entirely to get the "
                f"factory slot default."
            )
        value = user_knobs.pop(alias)
        rate_pos = pair["rate_pos"]
        sync_pos = pair["sync_pos"]
        if isinstance(value, bool):
            raise ValueError(
                f"{effect_name}.{alias} must be a number or division string, got bool"
            )
        if isinstance(value, (int, float)):
            lo, hi = _parse_dual_range(pair["encoding"])
            v = float(value)
            if v < lo or v > hi:
                raise ValueError(
                    f"{effect_name}.{alias} value {value} out of [{lo}, {hi}] "
                    f"(Sync=Off range per catalog)"
                )
            chunk[rate_pos] = v
            chunk[sync_pos] = 0.0
        elif isinstance(value, str):
            idx = _DIV_ENUM_11_BY_LABEL.get(value)
            if idx is None:
                raise ValueError(
                    f"{effect_name}.{alias}={value!r}: unknown div enum label. "
                    f"Valid options: {sorted(_DIV_ENUM_11_BY_LABEL)}"
                )
            chunk[rate_pos] = float(idx)
            chunk[sync_pos] = 1.0
        else:
            raise ValueError(
                f"{effect_name}.{alias} must be a number (ms/Hz) or string "
                f"(division), got {type(value).__name__}"
            )

    for label, value in user_knobs.items():
        if label not in positions:
            raise ValueError(
                f"unknown knob {label!r} on {effect_name}. "
                f"Available: {sorted(positions)}"
            )
        # Position convention detection: catalog uses absolute positions for cabs
        # (cat 0x0A) and slot-local positions for everything else. Normalize to local.
        raw_pos = positions[label]
        local_pos = raw_pos - slot_base if raw_pos >= 15 else raw_pos
        if not (0 <= local_pos < 15):
            raise ValueError(
                f"resolved position {local_pos} out of 0..14 for "
                f"{effect_name}.{label} (raw={raw_pos}, slot_base={slot_base})"
            )
        chunk[local_pos] = _encode_knob(
            value, encodings.get(label, ""), label, effect_name
        )

    return uid, chunk


# ──────────────────────────────────────────────────────────────────────────
#  Encoders
# ──────────────────────────────────────────────────────────────────────────
def encode_knob(value, knob_spec):
    enc = knob_spec["encoding"]
    if enc == "continuous_0_100":
        return float(max(0.0, min(100.0, float(value))))
    if enc == "enum_0_indexed":
        opts = knob_spec.get("options")
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        if isinstance(value, str):
            if opts is None:
                raise ValueError(
                    f"enum options not known for this knob — pass integer, got {value!r}"
                )
            if value not in opts:
                raise ValueError(f"enum value {value!r} not in {opts}")
            return float(opts.index(value))
        return float(int(value))
    raise ValueError(f"unsupported encoding {enc!r}")


# ──────────────────────────────────────────────────────────────────────────
#  Recipe → bytes
# ──────────────────────────────────────────────────────────────────────────
def build_preset(recipe: dict) -> bytes:
    # 1. name
    name = recipe["name"]
    if len(name) > 16:
        raise ValueError(f"name {name!r} is {len(name)} chars, max 16")

    # 2. init all slots at factory defaults
    algo_uid   = [FACTORY_DEFAULT_UID[s]              for s in SLOT_NAMES]
    algo_chunk = [deepcopy(FACTORY_DEFAULT_CHUNK[s])  for s in SLOT_NAMES]

    # 3. AMP slot
    amp_name = canonical_amp_name(recipe["amp"])
    if amp_name not in AMPS_BY_NAME:
        raise ValueError(f"unknown amp {amp_name!r}")
    amp = AMPS_BY_NAME[amp_name]

    algo_uid[SLOT_IDX["AMP"]] = int(amp["uid"], 16)

    # Start from the amp's own factory chunk (15 floats — includes gaps/engine_only)
    amp_chunk = list(amp["factory_chunk"])

    # Apply user-specified knob overrides
    user_knobs = recipe.get("knobs", {})
    for label, value in user_knobs.items():
        if label not in amp["knobs"]:
            raise ValueError(
                f"knob {label!r} not on {amp_name}. "
                f"Available: {sorted(amp['knobs'].keys())}"
            )
        spec = amp["knobs"][label]
        amp_chunk[spec["position"]] = encode_knob(value, spec)

    algo_chunk[SLOT_IDX["AMP"]] = amp_chunk

    # 4. CAB slot: three mutually-shaped paths (precedence: modules.CAB > cab > auto_cab)
    #    - modules.CAB: full module spec (handled in step 5, named-cab path)
    #    - recipe['cab']: shorthand, equivalent to modules.CAB with no knobs
    #    - recipe['auto_cab']: writes placeholder UID (device NVRAM decides)
    #    - none of the above: factory-default Gibby 1x10 (already set in step 2)
    modules = dict(recipe.get("modules") or {})
    if "cab" in recipe and "CAB" not in modules:
        # Promote recipe-level 'cab' shorthand into modules.CAB
        modules["CAB"] = {"effect": recipe["cab"], "knobs": {}}

    if recipe.get("auto_cab", False):
        if "CAB" in modules:
            raise ValueError(
                "recipe has both auto_cab=True and a named cab; "
                "these are mutually exclusive. Pick one."
            )
        algo_uid[SLOT_IDX["CAB"]] = AUTO_CAB_UID

    # 5. Modules — v0.4: FX2 reverb + CAB named cabs; other slots factory defaults
    for slot_name, mod_spec in modules.items():
        if slot_name not in SLOT_IDX:
            raise ValueError(f"unknown module slot {slot_name!r}")
        mod_uid, mod_chunk = _resolve_module(slot_name, mod_spec)
        algo_uid[SLOT_IDX[slot_name]] = mod_uid
        algo_chunk[SLOT_IDX[slot_name]] = mod_chunk

    # 6. Chain order
    chain_order = recipe.get("chain_order", ["DYN", "PRE", "AMP", "CAB", "EQ/MOD", "FX1", "FX2"])  # device stock chain (empirical, 4/4 community presets)
    algo_slot = [SLOT_IDX[s] for s in chain_order]
    if sorted(algo_slot) != list(range(7)):
        raise ValueError(f"chain_order must be a permutation of {SLOT_NAMES}")

    # 7. algoRunEn — enable-state is orthogonal to slot content.
    #
    #    If recipe has 'enabled_slots' (list of slot names), that is authoritative:
    #    exactly those slots are on, everything else is off. Allows any combination
    #    including all-on, all-off, or an enabled slot with factory-default content.
    #
    #    Otherwise, fall back to inference for backward compat with pre-v0.6 recipes:
    #      AMP always; CAB if auto_cab or explicit cab module; any slot with a module.
    #    Plus 'enabled_extra' for explicit opt-in to additional slots under inference.
    if "enabled_slots" in recipe:
        run_en = 0
        for slot in recipe["enabled_slots"]:
            if slot not in SLOT_IDX:
                raise ValueError(
                    f"invalid slot name {slot!r} in enabled_slots; "
                    f"must be one of {SLOT_NAMES}"
                )
            run_en |= SLOT_BIT[slot]
        # Guard against contradictory use of the legacy inference knobs alongside
        # an authoritative enabled_slots — they can't coexist coherently.
        if "enabled_extra" in recipe:
            raise ValueError(
                "recipe has both 'enabled_slots' (authoritative) and "
                "'enabled_extra' (inference-only); pick one"
            )
    else:
        run_en = SLOT_BIT["AMP"]
        if recipe.get("auto_cab", False) or "CAB" in modules:
            run_en |= SLOT_BIT["CAB"]
        for slot_name in modules.keys():
            run_en |= SLOT_BIT[slot_name]
        for slot in recipe.get("enabled_extra", []):
            run_en |= SLOT_BIT[slot]

    # 8. flatten
    algo_para_val = [f for chunk in algo_chunk for f in chunk]

    # 9. body
    body = {
        "magic":           23205,
        "crc16":           65535,
        "ID":              recipe.get("id", 1),
        "newType":         0,
        "name":            urllib.parse.quote(name),
        "volume":          recipe.get("volume", 100),
        "bpm":             recipe.get("bpm", 120),
        "algoRunEn":       run_en,
        "algoSlot":        algo_slot,
        "algoUID":         algo_uid,
        "algoParaVal":     algo_para_val,
        "quickKnobModule": [5, 6, 255, 255, 255, 255, 255, 255, 255, 255],
        "quickKnobParam":  [0, 0, 255, 255, 255, 255, 255, 255, 255, 255],
        "size":            536,
        "version":         1,
        "reserve":         [0] * 20,
    }

    # 10. header — two-pass for presetLenght
    body_json = json.dumps(body, separators=(",", ":"))
    header = {
        "presetVersion": "2.0.1", "fileType": "prst", "deviceType": "AP-10",
        "presetLenght": "0", "author": recipe.get("author", ""),
    }
    # Convention verified against Pulze Editor exports: presetLenght = BODY length only.
    header["presetLenght"] = str(len(body_json))
    header_json = json.dumps(header, separators=(",", ":"))
    return base64.b64encode((header_json + body_json).encode("utf-8"))


# ──────────────────────────────────────────────────────────────────────────
#  CLI
# ──────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("usage: preset_writer.py <recipe.json> <out.prst>", file=sys.stderr)
        sys.exit(1)
    recipe = json.loads(Path(sys.argv[1]).read_text())
    data   = build_preset(recipe)
    Path(sys.argv[2]).write_bytes(data)
    print(f"wrote {sys.argv[2]}  ({len(data)} bytes)")
