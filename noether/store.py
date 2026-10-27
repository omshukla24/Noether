"""Where sealed bundles and rate-limit counters are kept.

Vercel Blob when BLOB_READ_WRITE_TOKEN is set (the only durable place on a serverless host),
otherwise a local folder so the API runs in development without any account.
"""
from __future__ import annotations

import os
import re
import tempfile
import time
from pathlib import Path
from typing import Protocol

import httpx

BLOB_API = "https://vercel.com/api/blob"
BLOB_API_VERSION = "12"
_KEY = re.compile(r"[a-z0-9][a-z0-9._/-]{0,120}")
_RW_PREFIX = "vercel_blob_rw_"


class StoreError(Exception):
    """The store could not be read or written."""


class Store(Protocol):
    kind: str

    def put(self, key: str, data: bytes) -> None: ...

    def get(self, key: str, fresh: bool = False) -> bytes | None:
        """The bytes under `key`, or None when nothing is stored there. `fresh` skips any cache."""


def check_key(key: str) -> str:
    if not _KEY.fullmatch(key) or ".." in key or "//" in key or key.endswith("/"):
        raise StoreError(f"{key!r} is not a valid storage key")
    return key


class LocalStore:
    kind = "local"

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or os.environ.get("NOETHER_DATA_DIR") or Path(tempfile.gettempdir()) / "noether-data")

    def put(self, key: str, data: bytes) -> None:
        path = self.root / check_key(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_bytes(data)
            tmp.replace(path)
        except OSError as exc:
            raise StoreError(f"could not write {key}: {exc}") from exc

    def get(self, key: str, fresh: bool = False) -> bytes | None:
        path = self.root / check_key(key)
        try:
            return path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise StoreError(f"could not read {key}: {exc}") from exc


class BlobStore:
    """Vercel Blob over its REST API (the same calls the vercel-blob SDK makes), so the
    deploy needs no extra package. `access` must match the store's mode, fixed when the store was created."""
    kind = "blob"

    def __init__(self, token: str, access: str = "public", http: httpx.Client | None = None):
        if not token.startswith(_RW_PREFIX) or access not in ("public", "private"):
            raise StoreError("BLOB_READ_WRITE_TOKEN is not a read-write token, or the access mode is not public/private")
        self.token, self.access = token, access
        self.store_id = token[len(_RW_PREFIX):].split("_", 1)[0].lower()
        self.http = http or httpx.Client(timeout=20)

    def _auth(self) -> dict[str, str]:
        return {"authorization": f"Bearer {self.token}"}

    def put(self, key: str, data: bytes) -> None:
        headers = {**self._auth(), "x-api-version": BLOB_API_VERSION, "x-vercel-blob-access": self.access,
                   "x-allow-overwrite": "1", "x-add-random-suffix": "0", "x-content-type": "application/json",
                   "x-cache-control-max-age": "60"}
        try:
            response = self.http.put(BLOB_API, params={"pathname": check_key(key)}, content=data, headers=headers)
        except httpx.HTTPError as exc:
            raise StoreError(f"blob write failed: {exc}") from exc
        if response.status_code >= 300:
            raise StoreError(f"blob write answered HTTP {response.status_code}")

    def get(self, key: str, fresh: bool = False) -> bytes | None:
        url = f"https://{self.store_id}.{self.access}.blob.vercel-storage.com/{check_key(key)}"
        params = {"v": str(time.time_ns())} if fresh else None
        headers = self._auth() if self.access == "private" else {}
        try:
            response = self.http.get(url, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise StoreError(f"blob read failed: {exc}") from exc
        if response.status_code == 404:
            return None
        if response.status_code >= 300:
            raise StoreError(f"blob read answered HTTP {response.status_code}")
        return response.content


def make_store() -> Store:
    token = os.environ.get("BLOB_READ_WRITE_TOKEN", "").strip()
    if token:
        return BlobStore(token, os.environ.get("NOETHER_BLOB_ACCESS", "public"))
    return LocalStore()
