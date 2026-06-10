# Working in this repo

This is a complete white-box toolkit for Hotone Pulze / Pulze Mini presets. Everything
an AI needs to compose tones is machine-readable here:

- `pulze_tone/data/amps.json` — 62 amp entries: every knob's chunk position, encoding,
  range, options, factory default, plus reference text on what each model and knob does.
- `pulze_tone/data/EFFECT_CATALOG_v1.json` — 159 effect algorithms, same depth.
- `pulze_tone/writer.py` / `decoder.py` / `roundtrip.py` — recipe → bytes, bytes →
  fields, bytes → editable recipe.
- `tests/` — 40 byte-identity fixtures; run `python -m pytest tests/` after any change.

When a user asks for a tone, follow `.claude/skills/pulze-tone-generator/SKILL.md` —
including the optional first-run profile interview that personalizes generation
(instrument, upstream pedals, never-duplicate exclusions, Sound Clone / User IR slot
contents, gate/wet/enable/chain defaults, musical anchors). Profile answers live in
`user_layer.json`; explicit per-request instructions always override the profile.

Hard rules: specify every audible knob (unspecified positions encode as 0.0); preset
names ≤ 16 chars; never treat wild .prst files as default-value truth (firmware leaves
residue in unused positions); catalogs are device-verified ground truth — when a claim
and the catalog disagree, verify against a real device export before changing anything.
