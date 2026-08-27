# PyLens JA↔EN local pipeline — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evolve PyLens from whole-screenshot PP-OCRv3 + Google Translate into an offline Japanese↔English pipeline: skip-rules, glossary, cache, Argos MT, better OCR preprocess, optional tiled capture — without making WinOCR or the cloud required.

**Architecture:** Keep `capture/` and `overlay/`. Insert classifiers and caches in front of a new `translate/` adapter. Keep `OcrAdapter` factory; upgrade Paddle models behind `paddle_adapter.py`. Tiling is a preprocess step that still returns a single `list[TextBlock]` in capture-local coordinates.

**Tech Stack:** Python 3.11, PySide6, mss, PaddleOCR (v3 now, v5 after bench), argostranslate + CTranslate2, sqlite3, pytest.

**Spec:** `docs/superpowers/specs/2026-08-24-jp-en-local-pipeline-design.md`

## Global Constraints

- Languages this generation: Japanese and English only.
- No hard dependency on Windows OCR language packs.
- No Google / MyMemory required for the default path; cloud may remain a Settings opt-in later.
- Do not vendor NLLB (CC-BY-NC) or Surya weights.
- CPU-only must work; do not assume NVIDIA.
- Do not 3× upscale an entire 4K window; scale **crops** (or modest whole-image scale with a hard max).
- If tiling: overlap 8–12%, merge overlap boxes; do not split tiny regions.
- Skip translation for numbers, codes, dates, URLs, emails, currency, Excel formulas.
- User-facing overlay behavior stays: hotkey → overlay on the captured region.

## File map (create / modify)

| Path | Responsibility |
|---|---|
| `src/pylens/text/classify.py` | Skip vs translate; script detection |
| `src/pylens/text/normalize.py` | Cache keys, NFC, whitespace |
| `src/pylens/text/glossary.py` | Phrase/term lookup |
| `src/pylens/translate/cache.py` | SQLite + LRU |
| `src/pylens/translate/argos.py` | Offline JA↔EN |
| `src/pylens/translate/service.py` | Router: skip → glossary → cache → engine |
| `src/pylens/ocr/tiles.py` | Split/merge quadrants |
| `src/pylens/ocr/preprocess.py` | Per-crop / safer scale |
| `src/pylens/ocr/paddle_adapter.py` | v5 model URLs when approved |
| `src/pylens/settings.py` | Profile, engine, glossary path |
| `src/pylens/app.py` | Wire translator + profile |
| `data/glossary/ja_en.default.json` | Seed terms |
| `THIRD_PARTY_LICENSES.md` | Redistribution table |
| `tests/test_classify.py` | Skip-rules |
| `tests/test_glossary.py` | Longest-match |
| `tests/test_translate_cache.py` | Cache key + hit |
| `tests/test_tiles.py` | Overlap geometry + merge |
| `scripts/bench_ocr_mt.py` | Manual bench on user screenshots |

Do not rewrite overlay layout in this plan.

---

### Task 1: Text classifier (skip codes / dates / URLs)

**Files:**
- Create: `src/pylens/text/__init__.py`
- Create: `src/pylens/text/classify.py`
- Test: `tests/test_classify.py`

**Interfaces:**
- Consumes: raw OCR string
- Produces: `classify_span(text: str) -> Literal["skip", "ja", "en", "mixed"]`

- [ ] **Step 1: Write the failing tests**

```python
from pylens.text.classify import classify_span

def test_skip_numbers_ids_urls_formulas():
    for s in [
        "123456",
        "A00123",
        "2026/08/23",
        "2026-08-23",
        "¥120,000",
        "$5,000",
        "ABC-123",
        "https://example.com/a",
        "foo@yamaha-motor.com",
        "QSD01_01",
        "=SUM(A1:A10)",
        "SELECT * FROM T",
    ]:
        assert classify_span(s) == "skip", s

def test_japanese_and_english():
    assert classify_span("受注管理") == "ja"
    assert classify_span("Status") == "en"
```

- [ ] **Step 2: Run tests — expect fail**

Run: `pytest tests/test_classify.py -v`

- [ ] **Step 3: Implement `classify_span`**

Use regexes for URL, email, `=...`, ISO/JP dates, currency + digits, Excel-ish IDs (`[A-Z]{1,6}\d[\w\-]*`), digit-only / digit+comma/period. CJK unicode → `ja`. Latin letters without CJK → `en`. Mixed CJK+Latin → `mixed` (caller translates CJK spans only; reuse existing `_SEGMENT` logic from `translate/service.py`).

- [ ] **Step 4: Tests pass; commit** `test: add JA/EN skip classifier`

---

### Task 2: Normalization + translation cache

**Files:**
- Create: `src/pylens/text/normalize.py`
- Create: `src/pylens/translate/cache.py`
- Test: `tests/test_translate_cache.py`

**Interfaces:**
- `normalize_for_cache(text: str) -> str` — NFKC, squeeze whitespace, strip
- `cache_key(src: str, tgt: str, text: str) -> str` — sha256 hex
- `TranslationCache.get/set` — memory LRU (512) then SQLite at `appdata_dir() / "translation_cache.sqlite"`

- [ ] Tests: same text different unicode form hits cache; different tgt misses; skip empty.

- [ ] Table: `translations(key TEXT PRIMARY KEY, src TEXT, tgt TEXT, source TEXT, translated TEXT, created_at TEXT)`

- [ ] Commit: `feat: persist translation cache in AppData`

---

### Task 3: Glossary layer

**Files:**
- Create: `src/pylens/text/glossary.py`
- Create: `data/glossary/ja_en.default.json`
- Test: `tests/test_glossary.py`

**Interfaces:**
- `Glossary.from_paths(paths: list[Path])`
- `lookup(text: str, src: str, tgt: str) -> str | None` — exact match first, then longest substring replace for **whole tokens** (do not replace inside `受注番号` incorrectly: prefer exact full-string match for v1; token/phrase list for v2).

**v1 rule (YAGNI):** exact full-string match only. Safer for Excel cells.

Seed JSON:

```json
{
  "ja-en": {
    "受注": "Order",
    "発注": "Purchase Order",
    "売上": "Sales",
    "仕入": "Purchasing",
    "部品": "Parts",
    "車両": "Vehicle",
    "販売店": "Dealer",
    "国内": "Domestic",
    "海外": "Overseas"
  },
  "en-ja": {}
}
```

User file: `appdata_dir() / "glossary.json"` overlays defaults.

- [ ] Commit: `feat: exact-match JA/EN glossary`

---

### Task 4: Argos adapter + service router (cloud optional)

**Files:**
- Create: `src/pylens/translate/argos.py`
- Modify: `src/pylens/translate/service.py`
- Modify: `pyproject.toml` — extra `offline = ["argostranslate>=1.9"]`
- Modify: `src/pylens/settings.py` — `translate_engine: str = "argos"`  # argos | google
- Test: `tests/test_translate_parse.py` extended with skip+glossary mocks (no network)

**Interfaces:**
- `ArgosTranslator.available() -> bool`
- `ArgosTranslator.translate(text, src, tgt) -> str`
- `TranslationService.translate` order:
  1. classify skip → return original
  2. glossary exact → return
  3. cache get
  4. if engine argos: Argos; elif google: existing gtx/MyMemory
  5. cache set

Install models to `models/argos/` (project-local), not user home if we can set `ARGOS_PACKAGES_DIR` / documented Argos env. If Argos ignores env, install once via Settings “Download JA↔EN models”.

Packages (measured):

- `https://argos-net.com/v1/translate-ja_en-1_1.argosmodel` (111.7 MB)
- `https://argos-net.com/v1/translate-en_ja-1_1.argosmodel` (114.9 MB)

Default download: **ja→en only**. Checkbox for en→ja.

- [ ] Unit-test router with a fake engine (do not download 110 MB in CI).
- [ ] Manual: translate `受注管理システム` after glossary miss.
- [ ] Commit: `feat: offline Argos JA-EN with glossary and cache`

---

### Task 5: Safer OCR preprocess (biggest Excel win before swapping engines)

**Files:**
- Modify: `src/pylens/ocr/preprocess.py`
- Modify: `src/pylens/ocr/paddle_adapter.py` (call site)
- Test: `tests/test_ocr_adapters.py` or new `tests/test_preprocess.py`

**Change:**

- Replace global `TARGET_SCALE = 3.0` + `MAX_DIMENSION = 9000` with:
  - `choose_scale(w, h, profile)` → Fast: max side 1920; Balanced: max side 2560; Accuracy: max side 3200
  - Never produce a dimension > 4096 on CPU default
- Keep contrast/sharpen; add optional grayscale for Accuracy only (measure — color Excel headers sometimes matter)

- [ ] Commit: `fix: cap OCR upscale so Excel captures stay CPU-bound`

---

### Task 6: Optional 2×2 tiles with overlap

**Files:**
- Create: `src/pylens/ocr/tiles.py`
- Modify: `src/pylens/ocr/paddle_adapter.py` `recognize()`
- Test: `tests/test_tiles.py`

**Interfaces:**

```python
def should_tile(width: int, height: int, force: bool) -> bool:
    return force or (width >= 900 and height >= 700)

def split_quadrants(image, overlap_frac: float = 0.10) -> list[tuple[int, int, Image.Image]]:
    """Return (offset_x, offset_y, crop) in image pixels."""

def remap_blocks(blocks, offset_x, offset_y) -> list[TextBlock]: ...

def merge_overlap(blocks: list[TextBlock], iou_thresh: float = 0.5) -> list[TextBlock]: ...
```

- [ ] Tests: 100×100 never tiles; 1920×1080 tiles 4; overlap strips exist; duplicate identical text in overlap collapses to one box.
- [ ] Settings: `ocr_profile: fast | balanced | accuracy`; Accuracy sets `force_tiles=True` for window capture.
- [ ] Commit: `feat: overlapping quadrant OCR for large regions`

---

### Task 7: Benchmark harness (evidence before PP-OCRv5 bump)

**Files:**
- Create: `scripts/bench_ocr_mt.py`
- Create: `samples/README.md` (user drops PNG/JPG here; gitignore the images)

Script loads images from `samples/`, runs current adapter, prints box count, elapsed ms, sample texts. Second mode: Argos vs Google (Google only if user opts in).

- [ ] User runs on 5 Excel/PPT shots **before** changing paddle pins.
- [ ] Record numbers in `docs/superpowers/specs/` or a local `bench-results.md` (not required in git if screenshots are confidential).

- [ ] Commit: `chore: add OCR/MT bench script`

---

### Task 8: PP-OCRv5 mobile (only after Task 7)

**Files:**
- Modify: `src/pylens/ocr/paddle_adapter.py` `_JAPAN_MODEL_URLS`
- Modify: `pyproject.toml` if Paddle 3 / paddleocr 3 is required
- Modify: `THIRD_PARTY_LICENSES.md`

Measured URLs:

- det: `PP-OCRv5_mobile_det_infer.tar` (4.9 MB)
- rec: `PP-OCRv5_mobile_rec_infer.tar` (16.8 MB) — printed JA+EN in one rec model

Keep v3 paths as fallback if v5 init fails.

- [ ] Re-run bench; keep v3 if Excel accuracy regresses.
- [ ] Commit: `feat: optional PP-OCRv5 mobile Japanese-English OCR`

---

### Task 9: Settings + privacy copy

**Files:**
- Modify: `src/pylens/ui_settings.py`
- Modify: `README.md`

- Default translate engine: Argos.
- Buttons: download Argos ja-en; optional en-ja; optional v5 models.
- Privacy: default path does not send text off-box; Google remains explicit opt-in.
- Profile combo: Fast / Balanced / Accuracy.

- [ ] Commit: `feat: settings for offline MT and OCR profiles`

---

### Task 10: License inventory

**Files:**
- Create: `THIRD_PARTY_LICENSES.md`

Columns: component, version, code license, weight license, commercial redistribute?, attribution, URL.

Fill from spec table. Note Argos **packages** need a human check of the zip `metadata.json` / LICENSE inside each `.argosmodel` before Yamaha-wide bundle.

- [ ] Commit: `docs: third-party license matrix`

---

## Later (not this plan)

- Frame-diff / follow-window live OCR
- OPUS-MT CTranslate2 INT8 if Argos quality fails (Apache-2.0 self-convert)
- Server PP-OCRv5 (~85+88 MB) Accuracy-only
- User “correct this term” UI writing glossary.json
- Extra languages

## Execution order

Tasks 1–4 and 5–6 can proceed in parallel after 1 (classifier is independent of OCR). **Do not start Task 8 until Task 7 has numbers on real screenshots.**

## Spec coverage

| Spec item | Task |
|---|---|
| Skip codes/dates/URLs | 1 |
| Glossary | 3 |
| Cache | 2 |
| Argos offline | 4 |
| Cap upscale / Excel | 5 |
| 4 compartments | 6 |
| Bench before engine swap | 7 |
| PP-OCRv5 | 8 |
| No WinOCR required | unchanged factory; 9 copy |
| No NLLB/Surya | 10 + constraints |
| Licenses | 10 |
