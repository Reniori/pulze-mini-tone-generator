# Pulze Mini Tone Generator

Generate **Hotone Pulze / Pulze Mini** guitar tones as `.prst` preset files from a JSON
spec or a Python dict — or conversationally, as a Claude skill, using plain language
("warm SRV blues lead") backed by the complete reverse-engineered parameter catalogs.

Built and tested on a **Pulze Mini** (firmware V1.1.0). Community preset files from the
larger **Pulze** (Luna/Eclipse) decode byte-identically — same envelope, same
`deviceType "AP-10"`, same 7-slot × 15-param body, fully overlapping model catalog — so
generated presets load on both. Final as of the firmware version above; provided as-is
for posterity.

## Why this exists

Two reasons.

**The goal:** a semantic agent that can generate *any* preset from plain text — leaning on
a frontier AI's musical knowledge to build tones you don't yet know how to dial in
yourself. That requires machine-readable ground truth for every amp, cab, effect, and
knob position. This repo is that ground truth plus the byte-exact writer that turns a
recipe into a file. It was developed for a Pulze Mini resident on the **Busketeer 9000**
(a private guitar build with a 7-pedal onboard analog signal chain); this public fork
strips the private tone doctrine and ships pure device-factory defaults.

**The cautionary tale:** an early version carried a one-character documentation error —
"CAB High Cut Off sentinel = 2000" — when 2000 Hz is actually the filter's *floor*
(maximum filtering) and the true Off sentinel is 20001. The result: an entire 170-preset
library silently low-passed at 2 kHz. The empirical catalogs in this repo exist so that
folklore specs can never again outrank device truth. (Fellow travelers:
[THR-tone-architect](https://github.com/mctozal/THR-tone-architect) hit the same class of
bug on Yamaha THR-II and inspired this repo's publishing format.)

## The real `.prst` format

- Base64-encoded text: a JSON **header** immediately followed by a JSON **body**.
- Header: `{"presetVersion":"2.0.1","fileType":"prst","deviceType":"AP-10",
  "presetLenght":"<body length>","author":"..."}` — `presetLenght` counts the **body
  only** (verified against Pulze Editor exports; yes, the typo is the device's).
  `deviceType` is `"AP-10"` for both Pulze and Pulze Mini — there is **no device gate**.
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
`user_layer.example.json`). The file is informational — it never changes the bytes.

## As a Claude skill

`.claude/skills/pulze-tone-generator/SKILL.md` lets Claude compose tones
conversationally — ask for "a Pulze tone for …" and it picks the amp/cab/EQ/FX from the
catalogs, asks about your Sound Clone / User IR slots when relevant, and writes the file.

## Tests

```
pip install pytest && python3 -m pytest tests/
```

40 golden fixtures assert **byte-identical** round-trips (decode → recipe → rebuild).
CI runs the suite on every push.

## Verification notes

- Catalogs (`pulze_tone/data/`) are empirical: captured from a physical Pulze Mini on
  firmware V1.1.0 (fresh-load screenshots, byte-exact export round-trips). 62 amp
  entries including the 10 Sound Clone slots; 159 effects; every knob's chunk position
  and encoding.
- Format identity across devices was established on real community files from both the
  Pulze and Pulze Mini categories, multiple firmware generations: identical schema, full
  UID overlap, identical stock chain.
- Engine-only chunk positions (DSP-read values with no UI knob) are preserved per the
  catalogs; wild-file leftovers are deliberately not treated as defaults.

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

**声明：** 独立非官方项目，与 Hotone Audio 无关联。"Pulze""Hotone" 为长沙乐瞳
（Hotone Audio）商标。格式与映射均来自作者自有设备与文件的互操作性研究。
风险自负，请备份重要预设。MIT 许可。
