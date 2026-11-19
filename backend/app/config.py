"""Application configuration for CiteVerify.

Reads environment variables via python-dotenv.  All settings are exposed as
module-level constants so callers can do::

    from app.config import GEMINI_API_KEY, DB_PATH, ...

No I/O other than reading env vars happens at import time.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Locate .env relative to this file's package (backend/app/config.py)
# backend/ is two levels up from here.
# ---------------------------------------------------------------------------

_BACKEND_DIR: Path = Path(__file__).resolve().parent.parent  # backend/
_ENV_FILE: Path = _BACKEND_DIR / ".env"
load_dotenv(dotenv_path=_ENV_FILE, override=False)

# ---------------------------------------------------------------------------
# Crossref credentials & contact
# ---------------------------------------------------------------------------

CROSSREF_MAILTO: str = os.getenv("CROSSREF_MAILTO", "")

# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------

EMBEDDING_MODEL: str = os.getenv(
    "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

_db_path_raw: str = os.getenv("DB_PATH", "")
if _db_path_raw:
    DB_PATH: str = str(Path(_db_path_raw).resolve())
else:
    DB_PATH = str((_BACKEND_DIR / "verycite.db").resolve())

# ---------------------------------------------------------------------------
# Operational limits
# ---------------------------------------------------------------------------

MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
MAX_DOWNLOAD_SIZE_MB: int = int(os.getenv("MAX_DOWNLOAD_SIZE_MB", "20"))
PROVIDER_TIMEOUT: int = int(os.getenv("PROVIDER_TIMEOUT", "30"))
MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))


__all__ = [
    "CROSSREF_MAILTO",
    "EMBEDDING_MODEL",
    "DB_PATH",
    "MAX_FILE_SIZE_MB",
    "MAX_DOWNLOAD_SIZE_MB",
    "PROVIDER_TIMEOUT",
    "MAX_RETRIES",
]
