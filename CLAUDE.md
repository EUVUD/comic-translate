# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Comic Translate is a PySide6 desktop app that detects, OCRs, translates, inpaints and re-typesets text in comics (manga, webtoons, western comics). It targets Python 3.12. `requirements.txt` is the only dependency manifest: `pyproject.toml`, `uv.lock` and `.python-version` are gitignored because each developer generates them locally.

## Commands

```bash
uv init --python 3.12                           # first-time setup only
uv add -r requirements.txt --compile-bytecode   # install or update dependencies
uv pip install onnxruntime-gpu                  # optional, NVIDIA GPU acceleration
uv run comic.py                                 # launch the GUI
uv run comic.py path/to/file.ctpr               # launch and open a project
python -m compileall -q app modules pipeline imkit controller.py comic.py   # syntax check without Qt
python -m unittest discover -s tests -p '*_test.py'   # unit tests; run inside the project env (e.g. `uv run`)
python -m unittest discover -s tests -p 'test_*.py'   # older tests use this pattern; run both
python -m unittest tests.story_memory_schema_test     # a single test module
```

- Tests are unittest modules in `tests/`. Name new ones `*_test.py`: the root `.gitignore` ignores `test_*.py` (the few tracked `tests/test_*.py` were force-added). There is no linter, formatter or CI check, and `demo_*.py`, `benchmarks/` and `scripts` are gitignored.
- The `compileall` check always prints a `SyntaxWarning` from the vendored `modules/ocr/pororo/pororo/utils.py`. This warning is expected.
- The app is single-instance. A second `uv run comic.py` forwards its arguments to the running instance over a `QLocalServer` and exits (see `comic.py`). Close the running app before relaunching to test code changes.
- Account-backed tools require sign-in (`modules/utils/pipeline_config.py`). `validate_ocr` requires it only for `ACCOUNT_BACKED_OCR_TOOLS`. `validate_translator` requires it for every translator except a fully configured `Custom` endpoint. Default OCR, detection, inpainting and rendering work without an account.
- The only workflow, `.github/workflows/build-macos-dmg.yml` (manual dispatch), expects `ct-mac.spec` and `builddmg.sh`, which are not in the repo.

## Workflow

- Follow `AGENTS.md`: work incrementally, write a short step plan before adding functions, and explain any edit over 30 lines, then wait for the user's go-ahead.
- Features are specified as OpenSpec changes in `openspec/changes/<change>/` (proposal, design, tasks, specs). Each is developed on a `feature/<change>` branch cut from `develop` and merged back by PR. Validate with `openspec validate <change> --strict`, and tick `tasks.md` items as they land. The active change is `add-closed-loop-agent`.
- Commits use Conventional Commits with scopes, e.g. `feat(memory): …` or `docs(openspec): …`.

## Architecture

### Layers
- `comic.py` is the entry point. It shows the splash screen, enforces single-instance IPC, pre-imports `controller` on a background thread, installs Qt translations, then builds `ComicTranslate`.
- `controller.py`: `ComicTranslate` subclasses `app/ui/main_window.ComicTranslateUI` (widgets built by mixins in `app/ui/main_window/builders/`) and holds all application state. Behavior lives in `app/controllers/*`: `image_ctrl`, `text_ctrl`, `project_ctrl`, `webtoon_ctrl`, `manual_workflow_ctrl` and others. Each takes the main window as `self.main` and reads and writes its state directly. Many `ComicTranslate` methods are thin delegates to these controllers.
- `pipeline/`: `ComicTranslatePipeline` (`main_pipeline.py`) orchestrates the handlers for detection, OCR, translation, inpainting and segmentation. `BatchProcessor` handles normal batches and `WebtoonBatchProcessor` handles webtoon batches. The two batch processors share the handler instances and `CacheManager` (OCR and translation results keyed by image hash).
- `modules/` holds the engines: `detection`, `ocr`, `translation`, `inpainting`, `rendering` and `utils`. These should stay free of widget code. They receive the settings page as `settings` and call `settings.get_tool_selection(...)`, `get_credentials(...)` and `is_gpu_enabled()`.
- `imkit/` replaces OpenCV, which is not a dependency. It is built on PIL, mahotas and numpy, with cv2-like names such as `imk.read_image`, `imk.dilate` and `imk.find_contours`. Always use `import imkit as imk`. Images are RGB `uint8` numpy arrays; engines that need BGR convert internally.

### Threading
Heavy work goes through `main.run_threaded(fn, result_cb, error_cb, finished_cb, *args)` (`app/controllers/task_runner.py`). It queues operations and runs them one at a time as `GenericWorker`s on a `QThreadPool`. Callbacks are marshalled back to the GUI thread with `QTimer.singleShot(0, main, ...)`. `run_threaded_immediate` bypasses the queue.

Code running in a worker must not touch widgets. The pipeline reports back through the `ComicTranslate` signals `image_processed`, `patches_processed`, `blk_rendered`, `render_state_ready`, `image_skipped` and `progress_update`. Cancellation is cooperative: batch loops poll `main.current_worker.is_cancelled`. Errors go to `main.default_error_handler`, which maps `requests` HTTP errors and `modules/utils/exceptions.py` types to `app/ui/messages.Messages` dialogs.

### Per-page state
- `main.image_files` is the ordered list of page paths and the key for everything else. A path may be a lazy placeholder: an unextracted archive page (`FileHandler`) or a project blob (`project_state_v2`). Call `app.path_materialization.ensure_path_materialized(path)` before reading one from disk.
- `main.image_states[path]` is a dict with these keys:
  - `blk_list`
  - `source_lang` and `target_lang`, as canonical English names
  - `brush_strokes`
  - `skip`
  - `export_group_name`
  - `viewer_state`: the output of `ImageViewer.save_state()`, with keys `rectangles`, `text_items_state`, `transform`, `center` and `scene_rect`
- `main.blk_list` and the items in `main.image_viewer` are the live state of the displayed page only. On a page switch, `ImageStateController.save_image_state()` snapshots them into `image_states` and `load_image_state()` restores them. To change a page that isn't displayed, edit `image_states`.
- Batch results for other pages go straight into `image_states[path]['viewer_state']['text_items_state']` with `push_to_stack: True`. When that page is next loaded, those items are turned into undo commands.
- Undo uses one `QUndoStack` per page in `main.undo_stacks`, grouped in `main.undo_group`; `display_image` switches the active stack. Commands live in `app/ui/commands/`. Unsaved-changes and autosave tracking come from stack clean state plus `main.mark_project_dirty()`, so edits that bypass the undo stack must call `mark_project_dirty()`.

### TextBlock and project files
- `modules/utils/textblock.TextBlock` is the core record that flows through every stage. It holds `xyxy`, `bubble_xyxy`, `text_class` (`text_bubble`/`text_free`), detector `lines`, `script`, `source_lang`, `text`, `translation`, `font_color`, `direction` and more.
- Projects (`.ctpr`) are written by `app/projects/project_state_v2.py` as a SQLite file. It contains msgpack-encoded manifest and page rows plus content-addressed image blobs. The legacy format, a zip containing `state.msgpack`, is still readable.
- `app/projects/parsers.py` serializes a `TextBlock` as its `__dict__`. It restores one by updating a default-constructed `TextBlock()`. So a new `TextBlock` attribute needs three things:
  - a default in `__init__`, so older projects still load
  - an entry in `TextBlock.deep_copy()`
  - a msgpack-serializable value, or a new encoder/decoder pair in `parsers.py`
- `TextBlock.block_uuid` is the stable block identity that Story Memory relies on, and `deep_copy()` must preserve it.

### Engines, factories and models
- `DetectionEngineFactory`, `OCRFactory` and `TranslationFactory` cache engines in a class-level `_engines` dict. The key includes the model, the languages, the device, and a hash of credentials and LLM settings. `ComicTranslatePipeline.release_model_caches()` clears these caches after each batch.
- ONNX Runtime is the default backend. Torch is optional and not in `requirements.txt`: torch variants load only when `torch_available()`, and several torch files are gitignored (`modules/ocr/ppocr/torch`, `modules/inpainting/lama_arch`, …). `modules/utils/device.py` resolves the device and ONNX providers, and `modules/utils/onnx.py` creates sessions.
- Model weights are registered as `ModelID`/`ModelSpec` entries with sha256 checksums in `modules/utils/download.py`. Engines fetch them lazily with `ModelDownloader.get()`/`primary_path()` into `get_user_data_dir()/models` (on Linux, `~/.local/share/ComicTranslate/models`).
- Detection: RT-DETR-v2 finds text and bubble boxes, then `DetectionEngine.create_text_blocks` pairs them into `TextBlock`s. `modules/detection/heuristic_lines/` then computes per-block text lines. OCR engines crop these lines (`use_text_lines=True`), so line-detection changes directly affect OCR.
- OCR routing: `OCRProcessor` (`modules/ocr/processor.py`) chooses engines per language, or per detected script when the source language is `Auto`. The mapping in `OCRFactory._create_new_engine` is the source of truth, and it changes often; the engine list in the README is outdated.
- Translation: a signed-in user's translators, except `Custom`, go through `UserTranslator` to the Comic Translate web API (`app/account/config.py`). Account-backed OCR keys use `UserOCR` the same way. `Custom` is an OpenAI-compatible endpoint configured under Settings > Credentials.
- LLM translators receive the whole page as JSON, `{"block_0": text, ...}`, in `blk_list` order (`modules/utils/translator_utils.py`). The reply is mapped back by index, so the block order must not change between request and response. `MODEL_MAP` in the same file maps UI keys to provider model IDs.
- Story Memory keeps project canon, a Story Brief and approved translation memory inside the `.ctpr`. The code lives in `modules/translation/context/`, `app/projects/story_memory_*` and `pipeline/story_memory_context.py`. On every translation path, `prepare_story_memory_context` adds the matched subset to LLM prompts. `langgraph` is a dependency, but it must stay out of startup imports; `tests/test_translation_handler_imports.py` enforces this.

### Localization and canonical names
Every user-facing string is wrapped in `self.tr(...)` or `QCoreApplication.translate(context, ...)`. Internally, the code uses canonical English names.
- `main.lang_mapping` and `reverse_lang_mapping` map UI language labels to canonical names and back (`to_canonical_language_name` / `to_ui_language_label`).
- `SettingsPageUI.value_mappings` (`app/ui/settings/settings_ui.py`) does the same for settings saved to `QSettings("ComicLabs", "ComicTranslate")`.
- The processors map localized tool labels back to keys: `Translator._get_translator_key` and `OCRProcessor._get_ocr_key`.

Adding a translator or OCR option means touching all of these:
- `settings_ui.py`: the `supported_translators` or `ocr_engines` list, plus `value_mappings`
- the processor's key map
- the factory
- for translators, `MODEL_MAP`
- for account-backed OCR, `UserOCR.LLM_OCR_KEYS`/`FULL_PAGE_OCR_KEYS`

Qt translation sources are `resources/translations/ct_*.ts`, with paths relative to that folder. The compiled `resources/translations/compiled/ct_*.qm` files, loaded by `comic.py`, are committed alongside them.

### Webtoon mode
Webtoon mode stacks all pages vertically in one lazily loaded scene: `LazyWebtoonManager` plus `app/ui/canvas/webtoons/`. Per-page items are converted between page-local and scene coordinates by `coordinate_converter.py` and the `scene_items/*_manager.py` classes. Manual actions have separate webtoon paths (`*_webtoon_visible_area` in the pipeline and `webtoon_mode` branches in controllers). `WebtoonBatchProcessor` splits pages into virtual pages (`pipeline/virtual_page.py`) and stitches blocks that cross page seams. A per-page feature usually needs both a regular implementation and a webtoon implementation.

## Conventions
- Controllers and pipeline classes import `ComicTranslate` only under `TYPE_CHECKING` to avoid circular imports.
- Use the vendored `app/ui/dayu_widgets` components (`MPushButton`, `MMessage`, …) for UI; their icons live in `resources/static`. `modules/ocr/pororo/pororo` is also vendored code.
- `modules/ocr/ppocr/*.py` and `app/controllers/psd_exporter.py` are indented with tabs. All other files use 4 spaces. Keep each file's existing style.
- `controller.ENABLE_MEMLOGGER = True` turns on RSS logging at pipeline milestones (`modules/utils/memlog.py`).
