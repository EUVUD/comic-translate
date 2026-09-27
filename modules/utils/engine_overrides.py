"""Engine overrides for automated evaluation runs.

The detection, OCR, translation and inpainting factories check here before
building a real engine. The registry is empty in normal use. An evaluation
profile registers deterministic stand-in engines, so a job's outcome does not
depend on real models, networks or accounts.

Each factory callable receives the settings object first, then its kind's
arguments:

- ``detection``: ``(settings, model_name)``
- ``ocr``: ``(settings, source_lang_english, ocr_model)``
- ``translation``: ``(settings, source_lang, target_lang, translator_key)``
- ``inpainting``: ``(settings, inpainter_key)``
"""

from __future__ import annotations

from typing import Any, Callable

KINDS = ("detection", "ocr", "translation", "inpainting")

_factories: dict[str, Callable[..., Any]] = {}


def register(kind: str, factory: Callable[..., Any]) -> None:
    if kind not in KINDS:
        raise ValueError(f"unknown engine kind {kind!r}; expected one of {KINDS}")
    _factories[kind] = factory


def clear() -> None:
    _factories.clear()


def create(kind: str, *args: Any) -> Any | None:
    """Build the override engine for ``kind``, or return None when none is registered."""
    factory = _factories.get(kind)
    return None if factory is None else factory(*args)
