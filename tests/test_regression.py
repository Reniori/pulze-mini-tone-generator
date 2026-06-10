"""Byte-identity regression: every fixture must reconstruct -> rebuild -> byte-identical."""
from pathlib import Path
import pytest
from pulze_tone.roundtrip import recipe_from_prst
from pulze_tone.writer import build_preset

FIXTURES = sorted((Path(__file__).parent / "fixtures").glob("*.prst"))

@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda p: p.name)
def test_byte_identity(fixture):
    recipe = recipe_from_prst(fixture)
    assert build_preset(recipe) == fixture.read_bytes()

def test_fixture_count():
    assert len(FIXTURES) == 40

def test_slot_aliases():
    from pulze_tone.writer import canonical_amp_name, canonical_effect_name
    assert canonical_amp_name("Sound Clone 7") == "NAM 7"
    assert canonical_amp_name("sc 3") == "NAM 3"
    assert canonical_effect_name("User IR 12") == "Custom IR 12"
    assert canonical_effect_name("ir 1") == "Custom IR 1"
    assert canonical_amp_name("Black Twin") == "Black Twin"

def test_cab_factory_defaults():
    import base64, json
    from pulze_tone import build_preset as bp
    data = bp({"name": "T", "amp": "Jazz Clean",
               "modules": {"CAB": {"effect": "User IR 1", "knobs": {"Volume": 50}}},
               "enabled_slots": ["AMP", "CAB"]})
    dec = base64.b64decode(data).decode(); j = dec.index("}{")
    body = json.loads(dec[j+1:]); cab = body["algoParaVal"][45:60]
    assert cab[5] == 80.0 and cab[6] == 20001.0  # factory Low Cut 80 / High Cut Off

def test_off_sentinels_encodable():
    from pulze_tone import build_preset as bp
    bp({"name": "T2", "amp": "Jazz Clean",
        "modules": {"CAB": {"effect": "User IR 1",
                            "knobs": {"Volume": 50, "Low Cut": "Off", "High Cut": "Off"}}},
        "enabled_slots": ["AMP", "CAB"]})
