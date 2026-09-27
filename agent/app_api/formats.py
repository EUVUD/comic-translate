"""File formats the application reads and writes."""

from __future__ import annotations

import os

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".avif")
DOCUMENT_EXTENSIONS = (".pdf", ".epub")
ARCHIVE_EXTENSIONS = (".zip", ".rar", ".7z", ".tar", ".cbz", ".cbr", ".cb7", ".cbt")
PSD_EXTENSION = ".psd"
INPUT_EXTENSIONS = IMAGE_EXTENSIONS + DOCUMENT_EXTENSIONS + ARCHIVE_EXTENSIONS + (PSD_EXTENSION,)
EXPORT_EXTENSIONS = (".pdf", ".cbz", ".cb7", ".zip")


def count_pages(path: str | os.PathLike) -> int:
    """Pages in an exported PDF or comic archive."""
    path = os.fspath(path)
    extension = os.path.splitext(path)[1].lower()
    if extension == ".pdf":
        import pypdfium2

        document = pypdfium2.PdfDocument(path)
        try:
            return len(document)
        finally:
            document.close()
    if extension == ".cb7":
        import py7zr

        with py7zr.SevenZipFile(path, "r") as archive:
            names = archive.getnames()
    else:
        import zipfile

        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
    return sum(1 for name in names if name.lower().endswith(IMAGE_EXTENSIONS))
