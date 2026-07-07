# Repository Guidelines

## Project Structure & Module Organization

Comic Translate is a Python/PySide6 desktop app. The launcher is `comic.py`, and the main coordinator is `controller.py`. UI code lives under `app/ui/`, while user actions and state management live in `app/controllers/`. Core processing is split between `pipeline/` for orchestration and `modules/` for detection, OCR, translation, inpainting, rendering, and shared utilities. Project persistence is in `app/projects/`. Assets, icons, themes, and translation files are under `resources/`; localized README files are in `docs/`.

## Build, Test, and Development Commands

Use Python 3.12 as documented in `README.md`.

```bash
uv init --python 3.12
uv add -r requirements.txt --compile-bytecode
uv run comic.py
```

`uv run comic.py` starts the GUI. Some model files download on demand into the user data directory. There is no committed pytest, tox, or lint configuration, so validate with focused imports, smoke runs, and manual GUI checks relevant to the changed area.

## Coding Style & Naming Conventions

Use 4-space indentation and standard Python naming: `snake_case` for functions and variables, `PascalCase` for classes, and uppercase for constants. Prefer existing patterns. Keep Qt UI work on the GUI thread and use existing worker/thread helpers for long-running OCR, translation, inpainting, or file operations.

## Testing Guidelines

No formal test suite is present. For logic-only changes, add small targeted tests if you introduce a new isolated module. For GUI or model pipeline changes, smoke run `uv run comic.py` and exercise the affected workflow. For translation changes, verify both manual and batch paths where applicable.

## Commit & Pull Request Guidelines

Recent commits use short imperative summaries, for example `Improve block mask building and clipping` or `Route manga large blocks to PP-OCR`. Keep commits focused. Pull requests should include a concise summary, affected workflows, manual verification steps, and screenshots or screen recordings for visible UI changes.

## Agent-Specific Instructions

Work incrementally. Before adding functions, write a small step-by-step plan and implement one coherent step at a time rather than adding many functions in one change. If a proposed edit changes more than 30 lines, stop before editing and explain what the change does and why it is necessary. Continue only after the user says to keep moving.

## Security & Configuration Tips

Do not commit API keys, tokens, downloaded model files, or local data. Credentials are managed through app settings/keyring paths. Be careful when editing project persistence in `app/projects/project_state_v2.py`; `.ctpr` compatibility and lazy blob materialization are user-data sensitive.
