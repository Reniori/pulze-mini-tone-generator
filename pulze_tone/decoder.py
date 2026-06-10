"""decode_preset.py — reconstructed from generator code + existing doctrine.
Takes a .prst file (base64-encoded JSON header+body) and returns the parsed body dict.
"""
import base64
import json
from pathlib import Path


def decode_prst(path):
    raw = Path(path).read_text().strip()
    decoded = base64.b64decode(raw).decode("utf-8")
    # Find the end of the header (first complete top-level JSON object)
    depth = 0
    for i, c in enumerate(decoded):
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                header = json.loads(decoded[: i + 1])
                body = json.loads(decoded[i + 1 :])
                return header, body
    raise ValueError("malformed preset: no top-level header object found")


def slot_chunk(body, slot_id):
    """Return the 15-float chunk for a given slot (0..6)."""
    apv = body["algoParaVal"]
    return apv[slot_id * 15 : slot_id * 15 + 15]


SLOT_NAMES = {0: "PRE", 1: "AMP", 2: "DYN", 3: "CAB", 4: "EQ/MOD", 5: "FX1", 6: "FX2"}


def summarize(path):
    header, body = decode_prst(path)
    print(f"=== {Path(path).name} ===")
    print(f"name={body.get('name')!r}  bpm={body.get('bpm')}  volume={body.get('volume')}")
    print(f"algoRunEn={body.get('algoRunEn')}  algoSlot={body.get('algoSlot')}")
    uids = body.get("algoUID", [])
    for sid, uid in enumerate(uids):
        chunk = slot_chunk(body, sid)
        print(f"  slot {sid} ({SLOT_NAMES.get(sid, '?')}): UID=0x{uid:08X}  chunk={chunk}")
    return header, body


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        summarize(p)
