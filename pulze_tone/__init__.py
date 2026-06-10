"""Pulze Mini Tone Generator — generate Hotone Pulze / Pulze Mini .prst presets.

Public API:
    build_preset(recipe: dict) -> bytes      recipe dict -> .prst file bytes
    write_prst(recipe, out_dir) -> Path      build + write <name>.prst
    decode_prst(path) -> (header, body)      parse a .prst file
    recipe_from_prst(path) -> dict           reconstruct an editable recipe
"""
from pathlib import Path
from .writer import build_preset, canonical_amp_name, canonical_effect_name
from .decoder import decode_prst
from .roundtrip import recipe_from_prst

__version__ = "1.0.0"

def write_prst(recipe: dict, out_dir=".") -> Path:
    data = build_preset(recipe)
    p = Path(out_dir) / f"{recipe['name']}.prst"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p
