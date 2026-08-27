# PyLens Japanese ↔ English local pipeline — design spec

Date: 2026-08-24  
Status: draft for review (not yet implemented)

## Problem

PyLens today is a **one-shot** pipeline:

```
hotkey → mss capture → 3× upscale whole image → PP-OCRv3 Japanese → Google gtx / MyMemory → overlay
```

That design fights corporate use:

1. **Excel / dense UI** — small glyphs, grid lines, hundreds of boxes. Whole-image OCR at 3× (capped at 9000 px) is both slow and still too small per *character*.
2. **WinOCR** — optional fallback that needs a Windows language pack. Must not be a hard dependency.
3. **Google / MyMemory** — text leaves the PC; firewall and policy risk.
4. **Latency** — every capture re-OCRs and re-translates the entire region, including numbers, IDs, and repeated labels.

Language scope for this generation: **Japanese ↔ English only**. Other languages later.

## Goals

- Offline-capable JA↔EN overlay on Windows corporate PCs (CPU, no GPU assumed).
- Better dense-table OCR without a 650M-parameter document model.
- No required WinOCR; no required cloud translation.
- Skip translation for codes, numbers, dates, URLs, emails, currency, Excel formulas.
- Domain glossary + phrase cache so Yamaha-style terms stay consistent.
- Keep current capture + PySide overlay; evolve the middle of the pipeline.

## Non-goals (this generation)

- Surya / 90-language document OCR as a shipped engine (code Apache-2.0; **weights** are NC / revenue-capped — not a Yamaha-safe default).
- NLLB-200 as a shipped model (**CC-BY-NC-4.0** — research/non-commercial).
- Giant LLMs for per-cell translation.
- Live video OCR of the whole desktop (optional later; current product is hotkey one-shot).
- Blind 4-quadrant split without overlap + box merge (that cuts cells on the seams).

## Current stack (repo facts)

| Piece | Today |
|---|---|
| Capture | `mss` + region/window (`src/pylens/capture/`) |
| Preprocess | Contrast/sharpen + **3× LANCZOS**, `MAX_DIMENSION = 9000` (`ocr/preprocess.py`) |
| OCR primary | PaddleOCR **2.7.3** + **japan PP-OCRv3** rec + multilingual v3 det (`ocr/paddle_adapter.py`) |
| OCR fallback | Windows OCR (`ocr/windows_adapter.py`) |
| Translate | Google gtx → MyMemory; in-memory cache; CJK-vs-ASCII split (`translate/service.py`) |
| Overlay | PySide6 (`overlay/`) |
| On-disk OCR weights (this checkout) | det ~3.8 MB + rec ~11.4 MB + cls ~2.2 MB ≈ **17 MB** |

## Recommended architecture

Keep capture and overlay. Replace the middle with an **incremental, JA/EN-only vision pipeline**.

```
Capture (region or window)
    → optional 2×2 tiles with overlap (Accuracy / Excel mode)
    → preprocess (tile-level, not 3× of a 4K window)
    → PP-OCRv5 (ja+en+zh in one rec model)
    → merge boxes, drop junk
    → classify each string (skip / en / ja)
    → glossary hit?
    → translation cache hit?
    → Argos JA↔EN (CPU, CTranslate2 under the hood)
    → overlay
```

WinOCR stays an **optional** adapter, never required to start.

### Why not “OCR the whole 1920×1080 then translate everything”

Detectors struggle on huge dense grids. Characters need **pixel height**, not a giant canvas. Prefer: detect on a moderate-size image, then **upscale each crop** so the typical glyph is ~28–40 px tall before recognition.

### Quadrants — yes, with rules

User idea of 4 compartments is sound for **large Excel/PPT regions**, not as a blind default for a 400×200 tooltip.

Rules:

- Split only if `min(w,h) >= 900` **or** user selects Excel/dense profile.
- Overlap **8–12%** on each internal edge so cells on the cut are not bisected.
- Run tiles **sequentially on CPU** first (one Paddle instance). Parallel later if measured.
- Merge boxes with IoU / same-text de-dupe in the overlap strip.
- One-shot hotkey: **no frame-diff yet**. Frame-diff is Phase 3 if we add follow-window / repeat-capture.

### Hybrid OCR

- **Tier 1 (default):** PP-OCRv5 mobile det + PP-OCRv5 rec (printed JA/EN in one model, Apache-2.0).
- **Tier 2:** retry **low-confidence crops only** at higher scale / server rec (optional Accuracy profile).
- **Tier 3 (optional):** Windows OCR if the pack exists — never block install.

Do **not** ship Surya as default.

### Translation

- **Do not translate:** integers, decimals, IDs (`A00123`, `QSD01_01`), ISO/JP dates, `¥/$` money, URLs, emails, `=SUM(...)`, SQL-ish tokens already partly handled.
- **Preserve English** when target is English (and vice versa for Japanese).
- **Glossary JSON** (user + bundled Yamaha-ish seeds): exact and longest-phrase first.
- **Cache:** `sha256(src_lang + tgt_lang + normalized_text)` → SQLite under AppData, plus in-memory LRU.
- **Engine v1:** Argos Translate `ja→en` + `en→ja` packages (MIT code; packages are OPUS-family NMT, CPU via CTranslate2).
- **Engine v2 (only if quality fails):** self-converted **Helsinki-NLP OPUS-MT** via CTranslate2 INT8 (**Apache-2.0**). Do not vendor random HF “NLLB int8” repos (they inherit **CC-BY-NC**).

## Model size budget (measured / documented 2026-08-24)

| Component | Download size | License | Ship? |
|---|---|---|---|
| Current japan PP-OCRv3 rec+det+cls | **~17 MB** on disk | Apache-2.0 | Keep until v5 proven |
| PP-OCRv5 **mobile** det | **4.9 MB** tar | Apache-2.0 | **Default OCR** |
| PP-OCRv5 **mobile** rec (zh/en/ja) | **16.8 MB** tar | Apache-2.0 | **Default OCR** |
| PP-OCRv5 **server** rec | **84.9 MB** tar | Apache-2.0 | Accuracy profile only |
| PP-OCRv5 **server** det | **88.3 MB** tar | Apache-2.0 | Accuracy profile only |
| Argos `translate-ja_en-1_1.argosmodel` | **111.7 MB** | MIT wrapper; verify package README on install | **Default MT** |
| Argos `translate-en_ja-1_1.argosmodel` | **114.9 MB** | same | **Default MT** |
| OPUS-MT ja-en zip (CSC, 2019-12-18) | **267.6 MB** unconverted | Apache-2.0 | Convert offline if Argos quality insufficient |
| NLLB-200 600M (Meta or CT2 mirrors) | ~600–630 MB | **CC-BY-NC-4.0** | **Do not ship** |
| Surya weights | ~650M-class + Torch/vLLM | Weights **not** free for large-corp redistribution | **Do not ship** |

**Default offline bundle (v5 mobile + both Argos directions): ~248 MB models**, plus existing Paddle CPU wheel (already large). Target “core under ~200 MB” is realistic **if** we ship only `ja→en` first and add `en→ja` as an extra download — not if both directions are bundled.

Recommended ship:

- Always: OCR v5 mobile (~22 MB) + **Argos ja→en** (~112 MB) ≈ **134 MB**
- Optional download: Argos en→ja (~115 MB)
- Optional: server OCR (~173 MB extra) behind Accuracy

## Profiles

| Profile | OCR | Tiles | Translate | When |
|---|---|---|---|---|
| Fast | v5 mobile, no tile split unless huge | 1 | Argos + cache + skip-rules | PPT, web, dialogs |
| Balanced (default) | v5 mobile; tiles if region large | 1 or 4 | Argos; retry low-conf crops once | Most business screens |
| Accuracy | v5 server rec (and/or higher crop scale) | 4 with overlap | Argos; optional OPUS-CT2 later | Excel grids the user opts in |

## Licensing for Yamaha-style redistribution

Maintain `THIRD_PARTY_LICENSES.md`:

| Component | Code | Weights | Corporate redistribute |
|---|---|---|---|
| PaddleOCR / PP-OCRv5 | Apache-2.0 | Apache-2.0 | Yes |
| Argos Translate library | MIT | per-package | Library yes; **confirm each .argosmodel** before bundling |
| OPUS-MT (Helsinki-NLP) | Apache-2.0 | Apache-2.0 | Yes if we convert ourselves |
| NLLB-200 | — | CC-BY-NC | **No** |
| Surya | Apache-2.0 | NC / $5M cap / OpenRAIL-M | **No** as default |
| Windows OCR | OS component | Microsoft | Optional; do not depend |

Legal review still required internally; this spec is engineering guidance, not a legal opinion.

## Success criteria (must measure on *your* screenshots)

Pick 5–8 real captures: Excel dense sheet, PPT slide, SAP-like form, browser, mixed JA/EN toolbar.

For each profile record:

- OCR character / field error rate on Japanese labels
- Translation adequacy on 20 glossary terms
- Time to overlay (p50 / p95) on a CPU laptop
- Peak RAM
- On-disk model bytes

Do not choose v5 vs v3 or Argos vs Google from generic blogs.

## Risks

- **PaddleOCR 3.x / Paddle 3** vs current pin `paddleocr==2.7.3` / `paddlepaddle==2.6.2` — v5 may need a dependency bump; isolate behind the existing adapter.
- **Argos JA quality** on business nouns — glossary is the mitigation; OPUS-CT2 is the escape hatch.
- **Tile seams** — overlap + merge is mandatory.
- **Whole-image 3×** — likely hurts Excel more than it helps; replace with per-crop scale.

## Open decision (product)

Ship **both** Argos directions in the installer (~227 MB MT) vs **ja→en only** first (~112 MB). Default recommendation: ja→en bundled, en→ja optional, because overlay-to-English is the primary corporate reading path.
