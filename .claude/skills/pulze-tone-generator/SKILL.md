---
name: pulze-tone-generator
description: Generate Hotone Pulze / Pulze Mini .prst guitar presets from plain-language tone requests ("warm SRV blues lead", "tight djent rhythm"). Use whenever the user asks for a Pulze tone, preset, or .prst file.
---

# Pulze Tone Generator skill

Translate a tone request into a recipe dict, build it with this repo's writer, and hand
the user the `.prst` file (load via Pulze Editor → user slot).

## First run — profile interview (optional, skippable)

If `user_layer.json` does not exist next to the recipes, offer — don't force — a short
profile interview before the first build: "Want to answer a few setup questions so every
preset comes out tuned to your rig, or should I just build with sensible defaults?"
If they decline, build with factory-neutral assumptions and never ask again unless
invited. If they accept, ask in two or three small batches (never all at once), write
the answers into `user_layer.json` under `"profile"`, and apply them silently on every
composition afterward. An explicit instruction in any request always overrides the
profile.

The questions, each mapped to what it changes:

1. **Device & monitoring** — Pulze Mini or Pulze? Listening on the built-in speaker,
   headphones, or line-out to an interface/FRFR? → voicing of lows and presence,
   master-level headroom. (Small built-in speakers flatter mids; line-out tones can
   keep full low end.)
2. **Instrument & pickups** — humbuckers / single-coils / P90s / piezo / acoustic?
   Hot or vintage output? → gain staging and input assumptions for every preset.
3. **What sits between guitar and Pulze** — list any pedals always in line. → the AI
   treats that gain/compression as pre-established instead of recreating it digitally.
4. **Never-duplicate list** — effect types the AI should skip because hardware already
   covers them (e.g. "I have a Tube Screamer and a compressor on the board — never put
   those in a preset"). → hard exclusions in the PRE/DYN blocks.
5. **Sound Clone slots 1–10** — what NAM captures are loaded, slot by slot, with a
   word on character ("5: Hiwatt, huge clean headroom"). → unlocks "use my Hiwatt"
   requests and amp routing by tone semantics.
6. **User IR slots 1–20** — what's loaded, plus any favorite amp-cab pairings. →
   cab selection stops being generic.
7. **Gate policy** — noise gate on by default for high-gain? Tight chug or natural
   decay? → DYN block defaults and attack/release character.
8. **Wet taste** — bone-dry, subtle, or lush as the *default* for reverb/delay when
   the request doesn't say? → mix/decay starting ranges.
9. **Enable policy** — should effects ship ON, or loaded-but-bypassed so they're
   pre-dialed and waiting on the device? (Content and enablement are independent in
   this format.) → `enabled_slots` defaults.
10. **Default chain** — device stock order, or a standing custom order (e.g.
    "modulation always in front of the amp")? → `chain_order` default.
11. **Musical anchors** — main genres and three to five reference artists. → standing
    reference points when a request is vague.
12. **Naming scheme** — preset names cap at 16 characters; any prefix/convention
    wanted? → consistent, scannable names on the device.

## Composition workflow

1. Read the catalogs once: `pulze_tone/data/amps.json` (62 amps: name, knobs with
   positions/encodings/factory defaults, `notes_kit` descriptions) and
   `pulze_tone/data/EFFECT_CATALOG_v1.json` (159 effects: `params`,
   `param_chunk_positions`, `param_encodings`, `pdf_description`).
2. Load `user_layer.json` if present; apply `profile` (exclusions, gate/wet/enable/
   chain defaults, monitoring-aware voicing) and route Sound Clone / User IR requests
   through the slot descriptions. If the tone calls for user content and no file
   exists, ask whether they have Sound Clone (1-10) or User IR (1-20) slots loaded,
   or whether to use built-in amps/cabs only.
3. Compose the recipe (schema in README). Rules of thumb:
   - Specify every audible knob explicitly; unspecified knob positions become 0.0.
   - Many effects ship with Mix/Level at 0 — always set them.
   - Delay/mod Time/Rate: number = ms/Hz (Sync off), string "1/8d" = division (Sync on).
   - Cab Low Cut/High Cut accept "Off"; factory = Low Cut 80, High Cut Off.
   - Hi-gain amps benefit from Gate 2 in DYN (Threshold ~37, Attack 11-16, Release 58-75)
     unless the profile says otherwise.
   - Omit chain_order for the device stock chain; reorder for historical rigs
     (e.g. modulation in front of the amp) or per the profile's standing order.
   - Preset name ≤ 16 characters, following the profile's naming scheme if set.
4. Build and verify:
   ```python
   from pulze_tone import write_prst
   from pulze_tone.roundtrip import recipe_from_prst   # optional sanity decode
   write_prst(recipe, "output")
   ```
5. Deliver the file; describe the tone choices in one short paragraph, noting which
   profile rules shaped them.
