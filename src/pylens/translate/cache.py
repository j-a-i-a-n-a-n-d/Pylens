from __future__ import annotations

import sqlite3
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock

from pylens.text.normalize import cache_key, normalize_for_cache


class TranslationCache:
    """Small in-memory LRU backed by a persistent SQLite cache."""

    def __init__(self, database_path: Path, memory_limit: int = 512) -> None:
        self._memory_limit = max(1, memory_limit)
        self._memory: OrderedDict[str, str] = OrderedDict()
        self._lock = RLock()

        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(database_path, check_same_thread=False)
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS translations (
                key TEXT PRIMARY KEY,
                src TEXT NOT NULL,
                tgt TEXT NOT NULL,
                source TEXT NOT NULL,
                translated TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self._connection.commit()

    def get(self, source_lang: str, target_lang: str, text: str) -> str | None:
        normalized = normalize_for_cache(text)
        if not normalized:
            return None

        key = cache_key(source_lang, target_lang, normalized)
        with self._lock:
            memory_value = self._memory.get(key)
            if memory_value is not None:
                self._memory.move_to_end(key)
                return memory_value

            row = self._connection.execute(
                "SELECT translated FROM translations WHERE key = ?",
                (key,),
            ).fetchone()
            if row is None:
                return None

            translated = str(row[0])
            self._remember(key, translated)
            return translated

    def set(self, source_lang: str, target_lang: str, text: str, translated: str) -> None:
        normalized = normalize_for_cache(text)
        if not normalized:
            return

        key = cache_key(source_lang, target_lang, normalized)
        with self._lock:
            self._connection.execute(
                """
                INSERT OR REPLACE INTO translations
                    (key, src, tgt, source, translated, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    key,
                    source_lang.lower(),
                    target_lang.lower(),
                    normalized,
                    translated,
                    datetime.now(UTC).isoformat(),
                ),
            )
            self._connection.commit()
            self._remember(key, translated)

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _remember(self, key: str, translated: str) -> None:
        self._memory[key] = translated
        self._memory.move_to_end(key)
        while len(self._memory) > self._memory_limit:
            self._memory.popitem(last=False)
