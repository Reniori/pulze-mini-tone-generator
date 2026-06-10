---
name: pulze-tone-generator
description: Generate Hotone Pulze / Pulze Mini .prst guitar presets from plain-language tone requests ("warm SRV blues lead", "tight djent rhythm"). Use whenever the user asks for a Pulze tone, preset, or .prst file.
---

# Pulze Tone Generator skill

Translate a tone request into a recipe dict, build it with this repo's writer, and hand
the user the `.prst` file (load via Pulze Editor → user slot).

## Workflow

1. Read the catalogs once: `pulze_tone/data/amps.json` (62 amps: name, knobs with
   positions/encodings/factory defaults, `notes_kit` descriptions) and
   `pulze_tone/data/EFFECT_CATALOG_v1.json` (159 effects: `params`,
   `param_chunk_positions`, `param_encodings`, `pdf_description`).
2. If the tone calls for user content (NAM captures / custom IRs), check for
   `user_layer.json`; if absent, ask the user whether they have Sound Clone (1-10) or
   User IR (1-20) slots loaded, or whether to use built-in amps/cabs only.
3. Compose the recipe (schema in README). Rules of thumb:
   - Specify every audible knob explicitly; unspecified knob positions become 0.0.
   - Many effects ship with Mix/Level at 0 — always set them.
   - Delay/mod Time/Rate: number = ms/Hz (Sync off), string "1/8d" = division (Sync on).
   - Cab Low Cut/High Cut accept "Off"; factory = Low Cut 80, High Cut Off.
   - Hi-gain amps benefit from Gate 2 in DYN (Threshold ~37, Attack 11-16, Release 58-75).
   - Omit chain_order for the device stock chain; reorder for historical rigs
     (e.g. modulation in front of the amp).
   - Preset name ≤ 16 characters.
4. Build and verify:
```python
   from pulze_tone import write_prst
   from pulze_tone.roundtrip import recipe_from_prst   # optional sanity decode
   write_prst(recipe, "output")
```
5. Deliver the file; describe the tone choices in one short paragraph.
