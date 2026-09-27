"""Deterministic stand-in engines for evaluation runs, with scripted faults.

A fixture profile describes each input page, keyed by a fingerprint of its
pixels: the text blocks a detector finds and the text OCR reads there. It also
holds a translation table and a fault script. Once installed, it replaces the
detection, OCR, translation and inpainting engines through
``modules.utils.engine_overrides``, so a job's outcome depends only on how the
agent operates the application.

Profile format::

    {
      "pages": {"<fingerprint>": {"blocks": [
          {"xyxy": [x1, y1, x2, y2], "bubble_xyxy": [...] or null, "text": "..."}]}},
      "translations": {"<source text>": "<translation>"},
      "faults": [{"stage": "ocr", "page": "<fingerprint>", "error": "http_500", "times": 1}]
    }

A page without blocks behaves like a page where no text is detected.
Inpainting faults apply when the pipeline inpaints the whole page; patches
have their own fingerprints.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Mapping

import numpy as np
import requests

from modules.utils import engine_overrides
from modules.utils.exceptions import InsufficientCreditsException
from modules.utils.textblock import TextBlock

STAGES = ("detection", "ocr", "translation", "inpainting")
ERRORS = ("http_500", "connection", "timeout", "credits")


def page_fingerprint(image: np.ndarray) -> str:
    """Identity of a page's pixels, independent of its file name and format."""
    pixels = np.ascontiguousarray(image)
    digest = hashlib.sha256(f"{pixels.shape}|{pixels.dtype}|".encode())
    digest.update(pixels.tobytes())
    return digest.hexdigest()[:16]


@dataclass(frozen=True)
class Fault:
    stage: str
    page: str  # page fingerprint
    error: str
    times: int = 1  # calls that fail before the stage succeeds

    def __post_init__(self) -> None:
        if self.stage not in STAGES:
            raise ValueError(f"unknown fault stage {self.stage!r}; expected one of {STAGES}")
        if self.error not in ERRORS:
            raise ValueError(f"unknown fault error {self.error!r}; expected one of {ERRORS}")
        if self.times < 1:
            raise ValueError("a fault must fail at least once")


class FixtureProfile:
    def __init__(self, spec: Mapping[str, Any]) -> None:
        self.pages = {
            fingerprint: [dict(block) for block in page.get("blocks", [])]
            for fingerprint, page in spec.get("pages", {}).items()
        }
        self.translations = dict(spec.get("translations", {}))
        self.faults = [Fault(**fault) for fault in spec.get("faults", [])]
        self._failures_left = [fault.times for fault in self.faults]
        self.calls: list[tuple[str, str]] = []  # (stage, page fingerprint), in order

    def install(self) -> None:
        engines = {
            "detection": FixtureDetector(self),
            "ocr": FixtureOCR(self),
            "translation": FixtureTranslator(self),
            "inpainting": FixtureInpainter(self),
        }
        for kind, engine in engines.items():
            engine_overrides.register(kind, lambda *_args, engine=engine: engine)

    def uninstall(self) -> None:
        engine_overrides.clear()

    def enter(self, stage: str, fingerprint: str) -> None:
        """Record a call, and raise the scripted fault if one is still pending."""
        self.calls.append((stage, fingerprint))
        for index, fault in enumerate(self.faults):
            if fault.stage == stage and fault.page == fingerprint and self._failures_left[index]:
                self._failures_left[index] -= 1
                _raise(fault.error, stage)


def _raise(error: str, stage: str) -> None:
    message = f"scripted {error} fault in {stage}"
    if error == "http_500":
        response = requests.Response()
        response.status_code = 500
        raise requests.exceptions.HTTPError(message, response=response)
    if error == "connection":
        raise requests.exceptions.ConnectionError(message)
    if error == "timeout":
        raise requests.exceptions.Timeout(message)
    raise InsufficientCreditsException(message)


def _iou(a, b) -> float:
    ax1, ay1, ax2, ay2 = (float(v) for v in a)
    bx1, by1, bx2, by2 = (float(v) for v in b)
    width = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    height = max(0.0, min(ay2, by2) - max(ay1, by1))
    overlap = width * height
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - overlap
    return overlap / union if union > 0 else 0.0


class FixtureDetector:
    def __init__(self, profile: FixtureProfile) -> None:
        self.profile = profile

    def detect(self, image: np.ndarray) -> list[TextBlock]:
        fingerprint = page_fingerprint(image)
        self.profile.enter("detection", fingerprint)
        blocks = []
        for block in self.profile.pages.get(fingerprint, []):
            bubble = block.get("bubble_xyxy")
            blocks.append(TextBlock(
                text_bbox=np.array(block["xyxy"], dtype=np.int32),
                bubble_bbox=None if bubble is None else np.array(bubble, dtype=np.int32),
                text_class=block.get("text_class", "text_free" if bubble is None else "text_bubble"),
            ))
        return blocks


class FixtureOCR:
    def __init__(self, profile: FixtureProfile) -> None:
        self.profile = profile

    def initialize(self, **_kwargs: Any) -> None:
        return None

    def process_image(self, img: np.ndarray, blk_list: list[TextBlock]) -> list[TextBlock]:
        fingerprint = page_fingerprint(img)
        self.profile.enter("ocr", fingerprint)
        expected = self.profile.pages.get(fingerprint, [])
        for blk in blk_list:
            best = max(expected, key=lambda block: _iou(blk.xyxy, block["xyxy"]), default=None)
            matched = best is not None and _iou(blk.xyxy, best["xyxy"]) >= 0.5
            blk.text = best["text"] if matched else ""
        return blk_list


class FixtureTranslator:
    # Declared as an LLM-style engine so the pipeline passes the page image,
    # which lets translation faults be scripted per page.
    is_llm = True

    def __init__(self, profile: FixtureProfile) -> None:
        self.profile = profile

    def initialize(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def translate(self, blk_list: list[TextBlock], image: np.ndarray | None = None, extra_context: str = "") -> list[TextBlock]:
        self.profile.enter("translation", "" if image is None else page_fingerprint(image))
        for blk in blk_list:
            blk.translation = self.profile.translations.get(blk.text, "")
        return blk_list


class FixtureInpainter:
    """Paints masked pixels white, like a cleaned speech bubble."""

    def __init__(self, profile: FixtureProfile) -> None:
        self.profile = profile

    def __call__(self, image: np.ndarray, mask: np.ndarray, config: Any = None) -> np.ndarray:
        self.profile.enter("inpainting", page_fingerprint(image))
        # Same channel order as the input, like the real inpainters.
        result = np.array(image, copy=True)
        result[np.asarray(mask) > 0] = 255
        return result
