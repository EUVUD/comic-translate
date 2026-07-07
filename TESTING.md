# Testing Guide

Use Python 3.12 through `uv`, matching the project README.
## Set Up
```bash
uv init --python 3.12
uv add -r requirements.txt --compile-bytecode
```
Optional NVIDIA GPU runtime: `uv pip install onnxruntime-gpu`

## Start the App
```bash
uv run comic.py
```
## Focused Automated Checks
```bash
uv run python -m unittest tests.pipeline_config_test
uv run python -m unittest tests.download_file_ssl_test
uv run python -m py_compile modules/utils/pipeline_config.py modules/utils/download_file.py tests/pipeline_config_test.py tests/download_file_ssl_test.py
```
## Manual OCR Smoke Test
1. Open the app with `uv run comic.py`.
2. Go to `Settings > Tools` and set `Text Recognition` to `Default`.
3. Sign out, load an image, detect text, then click `Recognize`.
4. Confirm local OCR starts without asking you to sign in.
5. Switch `Text Recognition` to `Microsoft OCR` or `Gemini-2.5-Flash-Lite` while signed out.
6. Confirm those account-backed OCR tools still ask you to sign in.
