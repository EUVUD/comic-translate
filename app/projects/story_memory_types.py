"""Framework-independent value types shared by Story Memory layers."""

from __future__ import annotations

from dataclasses import dataclass


def _required_label(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value.strip()


@dataclass(frozen=True, slots=True)
class LanguagePair:
    """One Story Memory source and target language scope."""

    source_lang: str
    target_lang: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_lang", _required_label(self.source_lang, "source_lang"))
        object.__setattr__(self, "target_lang", _required_label(self.target_lang, "target_lang"))
