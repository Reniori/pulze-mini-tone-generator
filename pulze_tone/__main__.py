"""CLI: python3 -m pulze_tone [--spec recipe.json] [--decode file.prst] [--list WHAT] [-o DIR]"""
import argparse, json, sys
from pathlib import Path

def _lists(what):
    from .writer import AMPS_BY_NAME, _EFFECT_CATALOG
    if what in ("amps", "all"):
        print("== AMPS ==")
        for n in sorted(AMPS_BY_NAME): print(" ", n)
    if what in ("effects", "all"):
        print("== EFFECTS ==")
        for e in _EFFECT_CATALOG["effects"]: print(f"  {e['name']:<16s} [{e.get('subcat','?')}]")
    layer = Path("user_layer.json")
    if layer.exists():
        ul = json.loads(layer.read_text())
        print("== YOUR USER LAYER (user_layer.json) ==")
        for k, slots in ul.items():
            for s, info in sorted(slots.items(), key=lambda kv: int(kv[0])):
                print(f"  {k[:-1].replace('_',' ').title()} {s}: {info.get('name','?')} — {info.get('notes','')}")

def main(argv=None):
    ap = argparse.ArgumentParser(prog="pulze_tone",
        description="Generate / decode Hotone Pulze & Pulze Mini .prst presets")
    ap.add_argument("--spec", help="recipe JSON file to build")
    ap.add_argument("--decode", help=".prst file to decode back to a recipe (printed as JSON)")
    ap.add_argument("--list", nargs="?", const="all", choices=["amps", "effects", "all"],
                    help="list available amp / effect names (and your user_layer.json if present)")
    ap.add_argument("-o", "--out", default="output", help="output directory (default: output)")
    a = ap.parse_args(argv)

    if a.list:
        _lists(a.list); return 0
    if a.decode:
        from .roundtrip import recipe_from_prst
        print(json.dumps(recipe_from_prst(Path(a.decode)), indent=2)); return 0
    if a.spec:
        from . import write_prst
        recipe = json.loads(Path(a.spec).read_text())
        p = write_prst(recipe, a.out)
        print(f"wrote {p}  ({p.stat().st_size} bytes)"); return 0
    ap.print_help(); return 1

if __name__ == "__main__":
    sys.exit(main())
