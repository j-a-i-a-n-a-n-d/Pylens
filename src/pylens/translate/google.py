from __future__ import annotations

import json
import logging
from pathlib import Path
from tempfile import gettempdir
from urllib.parse import quote

import httpx

logger = logging.getLogger("pylens.translate")

GOOGLE_ENDPOINT = "https://translate.googleapis.com/translate_a/single"
MYMEMORY_ENDPOINT = "https://api.mymemory.translated.net/get"


class GoogleTranslator:
    """Existing online provider kept as an explicit compatibility option."""

    def __init__(self, timeout: float = 10.0) -> None:
        self._client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PyLens/0.1"},
        )
        self._log_path = Path(gettempdir()) / "pylens.log"

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        translated = self._try_google(text, source_lang, target_lang)
        if translated is not None:
            return translated
        translated = self._try_mymemory(text, source_lang, target_lang)
        return translated if translated is not None else text

    def prepare(self, source_lang: str, target_lang: str) -> None:
        _ = source_lang, target_lang

    def close(self) -> None:
        self._client.close()

    def _try_google(self, text: str, source_lang: str, target_lang: str) -> str | None:
        url = (
            f"{GOOGLE_ENDPOINT}?client=gtx&sl={source_lang}&tl={target_lang}"
            f"&dt=t&q={quote(text)}"
        )
        try:
            response = self._client.get(url)
            if response.status_code != 200 or not response.text.startswith("["):
                self._log(f"google http {response.status_code} for tgt={target_lang}")
                return None
            data = json.loads(response.text)
            sentences = data[0] if isinstance(data, list) and data else []
            parts = [
                sentence[0]
                for sentence in sentences
                if isinstance(sentence, list) and sentence and isinstance(sentence[0], str)
            ]
            return "".join(parts) or None
        except Exception as ex:
            self._log(f"google exception: {type(ex).__name__}: {ex}")
            return None

    def _try_mymemory(self, text: str, source_lang: str, target_lang: str) -> str | None:
        if source_lang == target_lang:
            return text
        url = f"{MYMEMORY_ENDPOINT}?q={quote(text)}&langpair={source_lang}|{target_lang}"
        try:
            response = self._client.get(url)
            if response.status_code != 200:
                self._log(f"mymemory http {response.status_code}")
                return None
            data = response.json()
            translated = data.get("responseData", {}).get("translatedText")
            return str(translated) if translated else None
        except Exception as ex:
            self._log(f"mymemory exception: {type(ex).__name__}: {ex}")
            return None

    def _log(self, line: str) -> None:
        try:
            from datetime import datetime

            with self._log_path.open("a", encoding="utf-8") as log:
                log.write(f"[{datetime.now():%H:%M:%S.%f}] {line}\n")
        except OSError:
            logger.debug("Could not write translation log", exc_info=True)
