# Manual offline model setup

PyLens does not download packages or models automatically.

## Folder prepared for Argos models

Place manually downloaded model archives in:

```text
models/argos/
├── translate-ja_en-1_1.argosmodel
└── translate-en_ja-1_1.argosmodel   (optional for the first phase)
```

Download sources:

- JA→EN: `https://argos-net.com/v1/translate-ja_en-1_1.argosmodel`
- EN→JA: `https://argos-net.com/v1/translate-en_ja-1_1.argosmodel`

Do not rename the files. Start with JA→EN only unless EN→JA is immediately
required.

## Folder prepared for offline Python wheels

On an internet-enabled machine with Python 3.11 and Windows x64, create a full
wheelhouse:

```powershell
py -3.11 -m pip download --only-binary=:all: --dest wheelhouse argostranslate
```

Copy every downloaded wheel into:

```text
vendor/wheels/
```

Do not install anything yet. After the files are present, PyLens can be
installed strictly from local files:

```powershell
.\.venv\Scripts\python.exe -m pip install --no-index --find-links vendor\wheels argostranslate
```

The development agent must wait for explicit confirmation before running that
local installation command.

## Licensing checkpoint

Before internal redistribution, inspect the archive metadata/license for each
`.argosmodel` and record it in `THIRD_PARTY_LICENSES.md`. Argos library code is
MIT; model-package licensing must be verified independently.
