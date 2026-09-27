from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

SNAPSHOT_SCHEMA = 1


def snapshot(window: Any, prompt_events: Iterable[Any] = ()) -> dict:
    """Describe the session's observable state as JSON-ready data.

    Call on the GUI thread. Tool names are canonical English, whatever the
    interface language.
    """
    settings_page = window.settings_page
    mappings = getattr(settings_page.ui, "value_mappings", {})

    def tool(kind: str) -> str:
        label = settings_page.get_tool_selection(kind)
        return mappings.get(label, label)

    return {
        "schema": SNAPSHOT_SCHEMA,
        "project_file": window.project_file,
        "unsaved_changes": bool(window.has_unsaved_changes()),
        "webtoon_mode": bool(window.webtoon_mode),
        "current_page": window.curr_img_idx,
        "settings": {
            "translator": tool("translator"),
            "ocr": tool("ocr"),
            "inpainter": tool("inpainter"),
            "detector": tool("detector"),
            "use_gpu": bool(settings_page.is_gpu_enabled()),
        },
        "pages": [_page(window, index, path) for index, path in enumerate(window.image_files)],
        "batch_report": _jsonable(window.batch_report_ctrl._latest_batch_report),
        "prompts": [asdict(event) for event in prompt_events],
    }


def _page(window: Any, index: int, path: str) -> dict:
    state = window.image_states.get(path, {})
    if index == window.curr_img_idx and not window.webtoon_mode:
        # The displayed page's live state is not saved back to image_states
        # until the user switches pages. Webtoon mode spans several pages at
        # once, so there the saved state is used.
        blocks = window.blk_list
        text_items = len(window.image_viewer.text_items)
    else:
        blocks = state.get("blk_list", [])
        text_items = len(state.get("viewer_state", {}).get("text_items_state", []))
    return {
        "index": index,
        "path": path,
        "name": os.path.basename(path),
        "skip": bool(state.get("skip", False)),
        "source_lang": state.get("source_lang"),
        "target_lang": state.get("target_lang"),
        "blocks": len(blocks),
        "translated_blocks": sum(1 for block in blocks if (getattr(block, "translation", "") or "").strip()),
        "text_items": text_items,
        # Cleaned regions painted over the original text.
        "inpainted_patches": len(window.image_patches.get(path, [])),
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def write_snapshot(data: dict, path: str | os.PathLike) -> Path:
    """Write ``data`` as JSON atomically, so a reader never sees a partial file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)
    return path
