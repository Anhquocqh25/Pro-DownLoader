from __future__ import annotations

import json
import logging
import re
import threading
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .core import DATA_DIR

logger = logging.getLogger("pro_downloader.translator")

TRANSLATION_CACHE_FILE = DATA_DIR / "translation_cache.json"
_cache_lock = threading.Lock()
_memory_cache: dict[str, str] | None = None

FORBIDDEN_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]')
HASHTAG_PATTERN = re.compile(r'#\S+')


def clean_title(text: str, max_length: int = 100, remove_hashtags: bool = True) -> str:
    """Cleans title by removing hashtags and forbidden characters, truncating cleanly."""
    if not text:
        return ""
    result = text.strip()
    if remove_hashtags:
        result = HASHTAG_PATTERN.sub('', result)
    # Normalize whitespace
    result = re.sub(r'\s+', ' ', result).strip()
    # Remove forbidden filename characters
    result = FORBIDDEN_FILENAME_CHARS.sub('', result).strip()
    if len(result) > max_length:
        # Truncate at last space if possible
        truncated = result[:max_length]
        last_space = truncated.rfind(' ')
        if last_space > max_length // 2:
            result = truncated[:last_space].strip() + '...'
        else:
            result = truncated.strip() + '...'
    return result or text.strip()


def load_translation_cache() -> dict[str, str]:
    global _memory_cache
    with _cache_lock:
        if _memory_cache is not None:
            return _memory_cache
        if TRANSLATION_CACHE_FILE.exists():
            try:
                with open(TRANSLATION_CACHE_FILE, "r", encoding="utf-8") as f:
                    _memory_cache = json.load(f)
                    return _memory_cache
            except Exception as exc:
                logger.warning("Failed to load translation cache: %s", exc)
        _memory_cache = {}
        return _memory_cache


def save_translation_cache() -> None:
    global _memory_cache
    with _cache_lock:
        if _memory_cache is None:
            return
        try:
            TRANSLATION_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(TRANSLATION_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(_memory_cache, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("Failed to save translation cache: %s", exc)


def translate_text(text: str, target: str = "vi", source: str = "auto") -> str:
    """Translates text to target language with caching and error tolerance."""
    cleaned_input = clean_title(text, max_length=200, remove_hashtags=True)
    if not cleaned_input:
        return text

    cache = load_translation_cache()
    cache_key = f"{source}->{target}:{cleaned_input}"
    if cache_key in cache:
        return cache[cache_key]

    url = (
        "https://translate.googleapis.com/translate_a/single?client=gtx"
        f"&sl={urllib.parse.quote(source)}&tl={urllib.parse.quote(target)}&dt=t"
        f"&q={urllib.parse.quote(cleaned_input)}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            translated_parts = [part[0] for part in data[0] if part and part[0]]
            translated = "".join(translated_parts).strip()
            translated = clean_title(translated, max_length=120, remove_hashtags=False)
            if translated:
                with _cache_lock:
                    cache[cache_key] = translated
                save_translation_cache()
                return translated
    except Exception as exc:
        logger.debug("Translation failed for '%s': %s", cleaned_input[:30], exc)

    return cleaned_input


def batch_translate_texts(texts: list[str], target: str = "vi", max_workers: int = 5) -> dict[str, str]:
    """Translates a list of texts concurrently, returning mapping from original to translated."""
    results: dict[str, str] = {}
    unique_texts = list(dict.fromkeys(texts))

    def _worker(t: str) -> tuple[str, str]:
        return t, translate_text(t, target=target)

    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(unique_texts)))) as executor:
        for orig, trans in executor.map(_worker, unique_texts):
            results[orig] = trans

    return results
