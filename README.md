# Pulze Mini Tone Generator

Generate **Hotone Pulze / Pulze Mini** guitar tones as `.prst` preset files from a JSON
spec or a Python dict — or, the way this is meant to be used, conversationally: through
Claude via the bundled skill, or any AI agent that can read the catalogs, using plain
language ("warm SRV blues lead") backed by complete reverse-engineered parameter
catalogs.

Built and tested on a **Pulze Mini** (firmware V1.1.0). Community preset files from the
larger **Pulze** (Luna/Eclipse) decode byte-identically — same envelope, same
`deviceType "AP-10"`, same 7-slot × 15-param body, fully overlapping model catalog — so
generated presets load on both. Final as of the firmware version above; provided as-is
for posterity.

This README is long on purpose. It contains the lore and the method, because the method
is the part most people don't have, and the lore explains why the method exists.

## Why this exists

The goal was always a semantic agent: describe a tone in plain language and get a
working preset back, leaning on a frontier AI's musical knowledge to build sounds I
didn't yet know how to dial in myself. That requires machine-readable ground truth for
every amp, cab, effect, and knob position on the device. This repo is that ground truth,
plus the byte-exact writer that turns a recipe into a file, plus the record of how a
person with zero programming experience got it done by working with an AI.

## What you can ask for

The point of a white-box model is that nothing is off-limits. Every block, knob,
encoding, and routing rule on the device is machine-readable in this repo, so an AI
composing with it has free rein over the entire signal chain — anything the firmware
accepts is fair game, and the firmware accepts everything:

- **Any block order.** All 5,040 orderings of the seven blocks are firmware-legal,
  and the writer takes a `chain_order` list verbatim. Modulation in front of the amp
  for vintage univibe throb; delay ahead of the drive for smeared, degraded repeats;
  cab before amp if you're curious what that does.
- **Doubled families.** FX1 and FX2 draw from shared pools — stack two reverbs (tight
  room feeding a huge hall), run two delays (slapback into a long dotted repeat), or
  pick which of delay and reverb feeds the other.
- **Blocks on, off, or loaded-off.** Content and enablement are independent: any block
  can ship fully voiced but bypassed, pre-dialed for the moment you engage it on the
  device. All seven on, all seven off, any mask in between.
- **Pedal-level requests.** Ask for "a Klon-style boost into a Plexi" or "a Tube
  Screamer pushing a tweed" and the names resolve to catalog models — every drive,
  comp, filter, and modulation entry carries reference text describing what it is and
  what each knob does, so the AI can look anything up mid-composition instead of
  guessing.
- **Real-gear translation.** The agent is also the translator layer: ask in the names
  you actually know — "a Marshall plexi," "a Fender Twin," "a Vox top boost" — and it
  maps them to the Hotone equivalents (Marshell for Marshall, and so on), because
  every catalog entry carries its real-world inspiration in the reference text. You
  never have to learn the device's renamed menu.
- **Context-aware chains.** Tell it the setting and the same request comes back voiced
  for it, case by case: bedroom solo gets the wide, lush wet and the full low end; a
  full band mix gets carved mids, a tighter low cut, and drier tails so the part sits
  instead of smearing.
- **Artist-grade specificity.** "Dotted-eighth delay in front of the amp, Edge style"
  yields the right division (`"1/8d"`, sync byte handled), sane feedback, and the
  chain reorder that puts the echo where it historically sat. "Gilmour lead" gets long
  repeats and a lush plate behind a flanger. "Surf" gets drippy spring plus tremolo at
  believable depth and rate. "EVH brown sound" gets the phaser and the tight slapback.
  "Ambient wash" stacks modulated delay into a long-decay reverb.
- **Knob-behavior precision.** Ranges, tapers, enum option labels, and factory
  defaults are all cataloged, so "gate sitting just under pick attack," "presence
  backed off a touch," or "delay mix at unity" become encoded values, not vibes.
- **Tone matching.** Describe a recording or name a track and the AI can iterate
  toward it, because every parameter is visible and writable — matching against a
  white box instead of poking at a black one. You can also `--decode` any community
  preset back to an editable recipe and ask for "this, but tighter."

All of it falls out of one fact: the building blocks are fully understood. Once every
UID, chunk position, encoding, and routing rule is documented, an AI doesn't need
factory presets to imitate — it composes from first principles, with the whole signal
chain as legal material. That is where the value of the catalogs lives.

## The story

I'm a photographer and instrument builder in Los Angeles. I have no coding background.
Across this entire project I never wrote a line of code — every Python script, every
byte-level decode, every catalog patch in this repo was written by Claude. What I
supplied was the device, the evidence, the methodology, the musical judgment, and the
stubbornness.

It started as a personal need. The Pulze Mini sits in my own custom guitar rig (the
Busketeer 9000, a Traveler Mod-X-platform guitar with 5 pickups across piezo and
magnetic, a 19k Super humbucker configuration, magnetic phase interaction like the Red
Special, an optical phase-and-gain whammy, onboard percussion elements, 2 active
circuits and 1 passive circuit with treble shaping and optical presence stages, and an
onboard EP > COMP > TS > MUFF > QDD > LOOP > Pulze signal chain, and more), the device
has 200 preset slots, and the official editing path is a phone app that moves one knob
at a time. Hotone ships no desktop editor at all — that phone app is the only official
tool that exists — so there was never an easier door to look for: everything had to
come out of mobile exports. I wanted a library organized the way I think,
and there was no programmatic way to make presets — the `.prst` format had no public
documentation anywhere. What came out of solving that personal problem is general: a
complete white-box model of the device that can compose any tone for anyone.

So the question became: can a non-programmer reverse-engineer a proprietary binary
format using an AI as the hands? The honest answer, twenty-some chat sessions later, is
yes — but not the way either of us expected.

An early session decoded what looked like the amp IDs, built a batch of presets, and
felt finished. Then the chat overflowed and hours of work vanished mid-session. Those
presets were never imported; they stayed throwaway. That loss founded the discipline
that carried everything after it: every session ends with a versioned freeze pack —
a zip containing the complete working state plus a nested copy of every prior version —
exported before the context runs out. Twenty-plus sessions deep, every prior state is
still recoverable. The original scope, "just identify amp IDs," turned out to be three
orders of magnitude smaller than the actual problem. Recognizing that gap and
continuing anyway was the project's first real decision.

The private side of the project — a 170-preset library across four tiers and a
composition doctrine tuned to my own rig — stays private. What you're looking at is
the general engine underneath it: the format knowledge, the catalogs, the writer, the
decoder, and the verification suite, with device-factory defaults and no personal tone
rules baked in. Publishing it at all was inspired by
[THR-tone-architect](https://github.com/mctozal/THR-tone-architect), which proved that
a hobbyist reverse-engineering toolkit for a single amp is worth shipping properly.

## How the format was deciphered — working with an AI on an undocumented binary

There was no spec. There was a device, a phone app that could export and import
`.prst` files, and an AI that could read whatever I uploaded. The whole method grew
from that triangle — and from one constraint: with zero coding experience, a visual
sweep was the only investigative move I logically knew how to make. So the method
became making sweeps count. There was a lot of sweeping; all of it was targeted.
These are the techniques, in roughly the order they were invented:

**The Rosetta Stone.** Wipe the device, export the factory-default preset, and treat
it as the canonical reference: every slot at a known model, every chunk in a known
state. One clean reference file resolved more ambiguity than the seventeen random
presets decoded before it. Orientation in unknown territory always started here.

**App-export diffs.** Change exactly one thing on the device — one knob, one toggle,
one model — export, and diff the two files. The position that changed is that
control's home. This is the highest-confidence evidence tier in the project: the app
itself telling you what it writes. Multi-toggle ambiguities, sync bytes, and
firmware-baked values were all resolved this way.

**K-sweeps.** To map an unknown effect's knobs in one shot, the AI generates a probe
preset with a distinctive placeholder per chunk position — `[11, 22, 33, 44, 55, 66,
77, 88]` — I sideload it, photograph the screen, and every knob's position falls out
of a single screenshot. (The earlier attempt used all 50s; the values collapsed
visually and taught us why the placeholders must be unique.)

**Screenshots as verification currency.** Fresh-load every effect and every amp,
photograph every knob, and let the AI read the images to lock per-knob factory
defaults into the catalog. All 52 built-in amp models and every factory effect — 159
unique algorithms covering the device's full effect set, some shared across multiple
slots — were swept this way. Screenshots were the silent handshake of the whole
collaboration: I rarely wrote "confirmed," I just uploaded the picture.

**The UID hunt.** Model identity itself was undocumented — every amp, cab, and effect
ID, which category each belongs to, and which slots accept which pools all had to be
established from nothing. The method: batches of numbered probe presets, each loading
candidate UIDs from a numeric range sweep, sideloaded to the device in bulk. My entire
reply for a batch was which preset numbers hit a real target — a named model on screen
instead of a fallback. Sweep the full range until every target is found; for the last
one or two stragglers, export that effect directly from the app and read its UID out
of the file, then look for the logic in the assignment. Sometimes there is none. The
economy move that made it bearable: the same confirmation screenshot already shows the
knob panel, so every UID hit doubled as a knob-layout and factory-default capture —
one photo, two data layers. The category byte fell out of the assembled map: it
encodes algorithm family, and slots accept families, which is why FX1 and FX2 share
pools at all.

**Enum archaeology.** Rotary selectors (voicings, modes, keys) store as integer
indices — but the mapping was never brute-forced one position at a time. There was no
"upload twenty screenshots of twenty knob positions." The real work was identifying
the small vocabulary of knob *types* Hotone actually uses, then characterizing each
type once: capture a knob's min and max, feed in the full label list the UI shows for
the range, and the endpoints plus the label sequence are generally enough to deduce
the entire enum chain. Once a type's logic is established it persists across every
other effect that uses it — the same division selector, the same signed-dB band, the
same mode switch — so new effects only needed label confirmation, never
re-derivation. (It's also how a wrong hypothesis — threshold-style encoding — died on
a single pair of targeted exports.) Screenshots, throughout, were about establishing
knob types across *all* parameters at once, their logic and their range, and letting
the types generalize. Some enums are effect-specific (harmonizer keys, intervals,
modes); a shared 11-value division enum (1/1 through 1/16) serves the time-based
effects. And some knobs are **dual-encoded**: a delay Time position holds either a
float in milliseconds or a division-enum index, disambiguated by a separate hidden
Sync byte. The writer accepts a number or a string like `"1/8d"` and sets the Sync
byte itself.

**Sentinels.** "Off" states live just outside the legal ranges: cab Low Cut sweeps
20–2000 Hz and Off is 19; High Cut sweeps 2000–20000 Hz and Off is 20001. Found by
exporting the Off states and reading what the app actually wrote.

**Engine-only positions.** Some chunk positions carry values the DSP reads but no UI
knob controls — they exist in every fresh export at positions no knob maps to. The
catalogs preserve these per effect and per slot, because zeroing them changes the
sound.

**Firmware residue.** The firmware does not zero unused chunk positions when you
switch models. Wild preset files — including everything on the community cloud —
carry leftover bytes from whatever was loaded before. Rule that followed: wild files
are evidence of structure, never of defaults. Only fresh-load captures count as
default-value truth.

**Cross-slot probes.** The same effect UID loaded into two different slots
simultaneously proved that UIDs anchor algorithms, not slots, and that slot index maps
identically into the UID array and the parameter chunks. The chain-order grammar was
brute-verified the same way: all 5040 orderings of the seven slots are legal to the
firmware, including cab-before-amp.

**Ground-truth correction.** When a generated preset was wrong on the device, I didn't
describe the bug — I fixed the knob in the app, exported the corrected file, and sent
it with "here is the preset for you to check." Diff against target. The bug locates
itself. This is how the nastiest writer bug was found: the catalog's knob `position`
field turned out to be the *visual* position in the app's layout, not the DSP chunk
position, and amps with layout gaps shifted every knob after the gap.

**The acceptance gate.** Every change to the writer or catalogs must rebuild a corpus
of device-verified presets byte-identically from their decoded recipes. That corpus —
40 fixtures — ships in `tests/` and runs in CI. A preset's lifecycle is: self-test
round-trip → ship → verify on device with screenshots → promote into the corpus.
Nothing is "done" at "the script ran without errors."

The honest scale of it: this was a lot of menial work. Generate a batch, sideload,
photograph, reply with the hit numbers, repeat — dozens of sweeps across hundreds of
models and knobs. The core reverse-engineering grind ran about a week of sustained
sessions on a Claude Max 5× subscription driving Claude Opus 4.7. It all worked out.

None of this is vibe coding. Vibe coding's defining feature is the absence of
verification; this project has verification at every layer, against the physical
device. But it
isn't conventional programming either — I can't audit the Python at the syntax level
and never tried to. The clean division of labor was the point: the AI did the
syntactic work; I did the empirical and architectural work; neither tried to do the
other's job.

## How a preset is built

A `.prst` file is base64-encoded text: one JSON header immediately followed by one
JSON body. The writer (`pulze_tone/writer.py`, dependency-free Python) compiles a
recipe dict into that file through a fixed pipeline:

1. **Name** — validated to ≤16 characters, URL-encoded into the body.
2. **Slot initialization** — all seven slots (`PRE, AMP, DYN, CAB, EQ/MOD, FX1, FX2`,
   internal order) get a default model UID and a 15-float parameter chunk. Empty slots
   receive the device's own default model with catalog-verified knob defaults plus
   that model's engine-only stamps.
3. **AMP resolution** — the chosen amp's catalog factory chunk is loaded whole
   (preserving its engine-only positions), then each recipe knob is encoded and
   overlaid at its catalog position.
4. **Module resolution** — each specified module resolves by name to a UID; its chunk
   is built from zeros, plus slot-appropriate engine-only stamps, plus the encoded
   recipe knobs. Cab-family effects start from the factory cab filter state instead
   (Volume 50, Low Cut 80 Hz, High Cut Off).
5. **Per-knob encoding dispatch** — each value routes through one of: continuous range
   clamp; 0-indexed or 1-indexed rotary enum (string label or integer accepted);
   toggle (`"On"`/`"Off"`/bool/0/1); Off-sentinel (the literal `"Off"` or the sentinel
   number, for knobs whose encoding declares one); or the dual-encoding gate, where a
   number writes a float with Sync=0 and a division string writes an enum index with
   Sync=1.
6. **Chain order** — the recipe's `chain_order` (or the device stock chain
   `DYN → PRE → AMP → CAB → EQ/MOD → FX1 → FX2` if omitted) becomes the `algoSlot`
   permutation.
7. **Enable mask** — `enabled_slots` becomes the `algoRunEn` bitmask, bit *i* =
   internal slot *i*. Content and enablement are orthogonal: a slot can carry a fully
   voiced effect and stay bypassed.
8. **Assembly** — the seven chunks flatten to 105 floats (`algoParaVal`); the body
   gains its constants (`magic` 23205, `crc16` 65535 — inert, confirmed by swap test —
   quick-knob defaults, zeroed reserve); the header is built with `presetLenght` equal
   to the body length exactly (the convention real Pulze Editor exports use — and yes,
   the typo is the device's); header + body encode to UTF-8 and then base64.

A body, trimmed to the load-bearing fields:

```jsonc
{
  "magic": 23205,
  "crc16": 65535,                 // unused by firmware
  "name": "Crunch%20Rhythm",      // URL-encoded, ≤16 chars
  "algoRunEn": 78,                // bitmask: AMP+DYN+CAB+FX2 enabled
  "algoSlot": [2,0,1,3,4,5,6],    // DYN→PRE→AMP→CAB→EQ/MOD→FX1→FX2
  "algoUID": [0, 117440555, 29, 167772265, 16777269, 67108876, 201326610],
  "algoParaVal": [ /* 7 × 15 floats, one chunk per internal slot */ ]
}
```

The decoder (`pulze_tone/decoder.py`) is the exact inverse, and
`pulze_tone/roundtrip.py` goes one step further: it reconstructs an *editable recipe*
from any `.prst` — including community downloads — by walking the catalogs backward
from the bytes. That reconstruction is what the test suite uses to prove the writer:
decode a fixture to a recipe, rebuild it, demand byte identity.

## The real `.prst` format

- Base64-encoded text: a JSON **header** immediately followed by a JSON **body**.
- Header: `{"presetVersion":"2.0.1","fileType":"prst","deviceType":"AP-10",
  "presetLenght":"<body length>","author":"..."}` — `presetLenght` counts the **body
  only** (verified against Pulze Editor exports). `deviceType` is `"AP-10"` for both
  Pulze and Pulze Mini — there is **no device gate** in the file.
- Body: `magic` 23205, `crc16` 65535 (unused), preset `ID`, `name` (URL-encoded,
  ≤16 chars), `volume`, `bpm`, then the engine state:
  - `algoSlot` — a permutation of slot IDs 0-6 defining signal-chain order. Internal
    slot order: `PRE, AMP, DYN, CAB, EQ/MOD, FX1, FX2`. The device stock chain is
    `[2,0,1,3,4,5,6]` = **DYN → PRE → AMP → CAB → EQ/MOD → FX1 → FX2** (empirical,
    consistent across every community preset sampled).
  - `algoUID` — one 32-bit UID per slot selecting the loaded model
    (`amps.json` / `EFFECT_CATALOG_v1.json` map every UID).
  - `algoRunEn` — enable bitmask, bit *i* = internal slot *i*.
  - `algoParaVal` — 7 × 15 floats, one 15-value chunk per slot. Every knob's chunk
    position, value encoding, range, and factory default is in the catalogs.
- Cab filters: **Low Cut** sweeps 20–2000 Hz, Off sentinel **19**; **High Cut** sweeps
  2000–20000 Hz, Off sentinel **20001**. Factory defaults: Low Cut 80 Hz, High Cut Off.
  Pass `"Off"` or the sentinel number; the writer handles both.
- Disabled slots in real device exports carry **leftover bytes** from prior state — the
  firmware does not zero them. Never read wild preset files as default-value truth.

## How this is meant to be used

Through an agent. The bundled Claude skill is the front door, but any AI that can read
the catalogs can drive this — you describe the tone, it composes the recipe, the writer
makes the file. On first contact the agent offers a short guided interview to establish
your baseline: rig, slots, exclusions, taste. Answer in plain language — any phrasing,
any level of detail. It isn't a form with one correct answer per field; the agent reads
context and fills the profile from whatever you give it, and you can revise any of it
later just by saying so.

The CLI and Python API below are deliberately minimal — a manual path for inspection
and scripting. The expected driver is the agent.

## Install

Pure standard-library Python 3.9+. No dependencies.

```
git clone https://github.com/reniori/pulze-mini-tone-generator && cd pulze-mini-tone-generator
python3 -m pulze_tone --list        # sanity check
```

## Usage

```
# From a spec file
python3 -m pulze_tone --spec my_tone.json -o output

# Decode any .prst (yours, or a community download) back to an editable recipe
python3 -m pulze_tone --decode Crossroads.prst

# Inspect available amps / effects (+ your user_layer.json if present)
python3 -m pulze_tone --list
```

### Recipe spec

```json
{
  "name": "Crunch Rhythm",
  "amp": "Marshell 45",
  "knobs": {"Gain": 55, "Presence": 52, "Master": 55, "Bass": 50, "Middle": 55, "Treble": 54},
  "modules": {
    "DYN":  {"effect": "Gate 2",     "knobs": {"Threshold": 37, "Attack": 15, "Release": 60}},
    "CAB":  {"effect": "Green 4x12", "knobs": {"Volume": 50}},
    "FX2":  {"effect": "Plate",      "knobs": {"Mix": 14, "Pre Dly": 25, "Decay": 45,
                                                "Low Damp": 60, "Hi Damp": 50, "Mod": 10}}
  },
  "enabled_slots": ["AMP", "CAB", "DYN", "FX2"]
}
```

Knob names, ranges, and option labels come from the catalogs. Delay/mod `Time`/`Rate`
accept a number (ms / Hz, Sync off) **or** a division string like `"1/8d"` (Sync on) —
the sync byte is set automatically. Omit `chain_order` to get the device stock chain.
Specify every audible knob: unspecified positions become 0.0, and several effects ship
with Mix or Level at 0 by factory default — silent until you set them.

### Python API

```python
from pulze_tone import write_prst
write_prst(spec_dict, "output")     # -> output/<name>.prst
```

Load the file onto the amp via **Pulze Editor** (BLE) — import, then save to a user slot.

## Sound Clone & User IR slots

Both devices have user-content slots the catalogs can only name, not describe:
**Sound Clone 1–10** (NAM captures, loaded via Pulze Editor) and **User IR 1–20**
(impulse responses). Address them by number in recipes — `"amp": "Sound Clone 7"`,
`"effect": "User IR 12"` (aliases `SC 7`, `NAM 7`, `IR 12`, `Custom IR 12` all work).

To let an AI assistant route plain-language tone requests through *your* content,
describe what you loaded in a `user_layer.json` next to your recipes (see
`user_layer.example.json`). The same file carries an optional `profile` section — your
rig, exclusions, and taste defaults from the skill's starter interview. It is
informational — it never changes the bytes, only the choices.

## As a Claude skill

`.claude/skills/pulze-tone-generator/SKILL.md` lets Claude compose tones
conversationally — ask for "a Pulze tone for …" and it picks the amp/cab/EQ/FX from the
catalogs, asks about your Sound Clone / User IR slots when relevant, and writes the
file. On first run it offers a short, skippable **profile interview** — device and
monitoring, instrument and pickups, pedals already on your board (so the AI never
duplicates them digitally), slot contents, gate/wet/enable/chain preferences, musical
anchors, naming scheme — and stores the answers in `user_layer.json` so every later
preset is tuned to your rig from the first word. A root `CLAUDE.md` orients Claude Code
the same way. This is the semantic agent the project was built for, running on the
catalogs as its ground truth.

## Tests

```
pip install pytest && python3 -m pytest tests/
```

40 golden fixtures assert **byte-identical** round-trips (decode → recipe → rebuild).
The fixtures descend from device-verified presets; the suite is the same acceptance
gate the project ran after every catalog or writer change. CI runs it on every push.

## Verification notes

- Catalogs (`pulze_tone/data/`) are empirical: captured from a physical Pulze Mini on
  firmware V1.1.0 via fresh-load screenshots, single-knob export diffs, K-sweep
  probes, and byte-exact export round-trips. 62 amp entries (52 built-in models + the
  10 Sound Clone slots); 159 unique effect algorithms; every knob's chunk position,
  encoding, range, option labels, and factory default.
- Format identity across devices was established on real community files from both the
  Pulze and Pulze Mini categories, multiple firmware generations: identical schema,
  full UID overlap, identical stock chain.
- Engine-only chunk positions (DSP-read values with no UI knob) are preserved per the
  catalogs; wild-file leftovers are deliberately not treated as defaults.
- Where any document and the device disagreed, the device won, every time. The
  catalogs encode only what survived that filter.

## Credits

Every line of code in this repository was written by Claude (Anthropic), working under
my direction across a long series of chat sessions; every byte-level fact in the
catalogs was verified against the physical device before it was allowed to stay. The
decision to publish, and the shape of this repo, were inspired by
[mctozal/THR-tone-architect](https://github.com/mctozal/THR-tone-architect), the
equivalent project for the Yamaha THR-II.

## Disclaimer

Independent, unofficial project — not affiliated with or endorsed by Hotone Audio.
"Pulze" and "Hotone" are trademarks of Changsha Hotone Audio Co., Ltd. The format and
model mappings were derived from the owner's own device and files for interoperability.
Use at your own risk; back up presets you care about.

## License

MIT — see [LICENSE](LICENSE).

---

# Pulze Mini 音色生成器（简体中文）

用 JSON 配方或 Python 字典生成 **Hotone Pulze / Pulze Mini** 的 `.prst` 音色预设文件；
也可作为 Claude 技能，用自然语言（例如"温暖的 SRV 布鲁斯主音"）直接生成 —— 背后是完整
逆向整理的参数目录（每个放大器、箱体、效果器、每个旋钮位置）。

在 **Pulze Mini**（固件 V1.1.0）上构建并实测；大款 Pulze 的社区预设文件与 Mini 字节级
同构（同一封装、同一 `deviceType "AP-10"`、同一 7 槽 × 15 参数结构、型号目录完全重叠），
生成的预设两款设备均可加载。随当前固件版本定稿，按"原样"长期存档。

**项目背景：** 作者是洛杉矶的摄影师与乐器制作者，完全没有编程背景，全程没有写过一行
代码 —— 仓库中所有代码均由 Claude（AI）在作者指导下完成。作者提供设备、实证证据、
方法论与音乐判断：通过出厂复位导出建立"罗塞塔石碑"参照、单旋钮导出差分定位每个参数
的字节位置、K-sweep 探针（每个位置一个独特占位值）一张截图映射全部旋钮、逐档导出
破解枚举编码、以及"自检 → 出货 → 设备截图验证 → 收录回归库"的验收闭环。AI 的论断
一律视为假设，以设备字节为最终裁决 —— 这是整个项目最重要的纪律。完整故事与方法见
上文英文章节。

**要点：**

- `.prst` = Base64 编码的 JSON 头 + JSON 体；`presetLenght` 只计正文长度。
- 信号链顺序由 `algoSlot` 排列定义；设备出厂默认链为
  **DYN → PRE → AMP → CAB → EQ/MOD → FX1 → FX2**。
- 箱体滤波：Low Cut 20–2000 Hz（Off 哨兵值 19）；High Cut 2000–20000 Hz（Off 哨兵值
  20001）。出厂默认 Low Cut 80 Hz、High Cut Off。配方里写 `"Off"` 或哨兵数值均可。
- **Sound Clone 1–10**（NAM 采样槽）与 **User IR 1–20**（用户 IR 槽）按编号寻址，
  例如 `"amp": "Sound Clone 7"`；可选的 `user_layer.json` 用来描述你自己装载的内容，
  方便 AI 按音色语义路由。
- 安装：纯标准库 Python 3.9+，零依赖。`python3 -m pulze_tone --list` 自检；
  `--spec 配方.json -o output` 生成；`--decode 文件.prst` 反解为可编辑配方。
- 生成的文件用 **Pulze Editor** 导入设备并存入用户槽位。
- **预期用法：** 通过 Claude（内置技能）或任意 AI 代理对话式生成；首次使用有一段
  引导式基线问答，可用任何自然语言自由作答 —— 不限定标准答案，代理会理解上下文并随时
  按你的话修改；命令行仅作为最简手动通道。可直接说真实型号名（如 Marshall、Fender
  Twin），代理自动映射到 Hotone 等价型号（Marshell 等），并按独奏或乐队合奏等使用场景
  逐例调整信号链。
- **白盒自由度：** 七个模块任意排序（共 5040 种顺序全部合法，调制放前级、箱体放放大器
  之前都行）；FX1/FX2 共享效果池，可叠两个混响或两个延迟；模块可"装载但旁通"；可用
  踏板语言点名（Klon 类、TS 类自动映射到目录型号）；按艺术家描述自动给出正确的附点
  延迟与链位；也可让 AI 对照录音做音色匹配，或用 `--decode` 反解社区预设再修改。

**声明：** 独立非官方项目，与 Hotone Audio 无关联。"Pulze""Hotone" 为长沙乐瞳
（Hotone Audio）商标。格式与映射均来自作者自有设备与文件的互操作性研究。
风险自负，请备份重要预设。MIT 许可。
