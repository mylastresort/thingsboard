"""
ModelStorageService — orchestrates save / load with configurable fallback.

The primary backend defaults to MinIO; if it is unreachable the service
transparently falls back to the secondary backend (PostgreSQL blobs) and
optionally mirrors artifacts to the local filesystem so that in-process
load_models() / model.load() paths remain unchanged.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List, Optional

from .backends import (
    LocalStorageBackend,
    MinIOStorageBackend,
    ModelStorageBackend,
    PostgresStorageBackend,
)

logger = logging.getLogger(__name__)

_STRATEGY_ENV = "MODEL_STORAGE_STRATEGY"


def _build_backend(name: str) -> ModelStorageBackend:
    name = name.strip().lower()
    if name == "minio":
        return MinIOStorageBackend()
    if name == "postgres":
        return PostgresStorageBackend()
    if name == "local":
        return LocalStorageBackend()
    raise ValueError(f"Unknown storage strategy: {name!r}")


class ModelStorageService:
    """Facade that saves/loads model directories across backends."""

    def __init__(
        self,
        primary: ModelStorageBackend | None = None,
        fallback: ModelStorageBackend | None = None,
        local_mirror: LocalStorageBackend | None = None,
    ) -> None:
        strategy = os.getenv(_STRATEGY_ENV, "minio")
        self._primary = primary or _build_backend(strategy)
        self._fallback = fallback or PostgresStorageBackend()
        self._mirror = local_mirror or LocalStorageBackend()
        logger.info(
            "ModelStorageService initialised: primary=%s, fallback=PostgresStorageBackend, mirror=local",
            type(self._primary).__name__,
        )

    # ── public API ──────────────────────────────────────────────────────

    def save_model(self, model_id: str, model_dir: Path) -> None:
        """Persist every file in *model_dir* to primary, fallback, and local mirror."""
        model_dir = Path(model_dir)
        if not model_dir.is_dir():
            raise FileNotFoundError(f"Model directory not found: {model_dir}")

        for artifact in model_dir.iterdir():
            if not artifact.is_file():
                continue
            data = artifact.read_bytes()
            self._put_with_fallback(model_id, artifact.name, data)

        logger.info(
            "Saved model %s (%d artifacts)", model_id, self._count_files(model_dir)
        )

    def load_model(self, model_id: str, target_dir: Path) -> Path:
        """Load model artifacts into *target_dir* and return it as a Path.

        Tries primary → fallback → local mirror.  If only the mirror has the
        files (e.g. from a previous local save) the data is returned from
        disk.
        """
        target_dir = Path(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        files = self._list_with_fallback(model_id)
        if not files:
            raise FileNotFoundError(f"No artifacts found for model {model_id}")

        for filename in files:
            target = target_dir / filename
            if target.exists():
                continue
            data = self._get_with_fallback(model_id, filename)
            target.write_bytes(data)

        logger.info("Loaded model %s into %s (%d files)", model_id, target_dir, len(files))
        return target_dir

    def delete_model(self, model_id: str) -> None:
        """Remove a model from all backends."""
        for backend in (self._primary, self._fallback, self._mirror):
            try:
                for filename in backend.list_files(model_id):
                    backend.delete(model_id, filename)
            except Exception as exc:
                logger.warning(
                    "Error deleting %s from %s: %s",
                    model_id,
                    type(backend).__name__,
                    exc,
                )
        logger.info("Deleted model %s from all backends", model_id)

    def exists(self, model_id: str, filename: str | None = None) -> bool:
        """Check existence.  If *filename* is None, checks any artifact."""
        if filename:
            return (
                self._primary.exists(model_id, filename)
                or self._fallback.exists(model_id, filename)
                or self._mirror.exists(model_id, filename)
            )
        return bool(self.list_files(model_id))

    def list_files(self, model_id: str) -> List[str]:
        return self._list_with_fallback(model_id)

    # ── internal helpers ────────────────────────────────────────────────

    def _put_with_fallback(self, model_id: str, filename: str, data: bytes) -> None:
        # Always mirror locally
        try:
            self._mirror.put(model_id, filename, data)
        except Exception as exc:
            logger.warning("Local mirror PUT failed: %s", exc)

        # Try primary
        try:
            self._primary.put(model_id, filename, data)
            return
        except Exception as exc:
            logger.warning("Primary PUT failed (%s), falling back: %s", type(self._primary).__name__, exc)

        # Fallback
        try:
            self._fallback.put(model_id, filename, data)
        except Exception as exc:
            logger.error("Fallback PUT also failed: %s", exc)

    def _get_with_fallback(self, model_id: str, filename: str) -> bytes:
        # Try primary
        try:
            return self._primary.get(model_id, filename)
        except Exception as exc:
            logger.warning("Primary GET failed (%s): %s", type(self._primary).__name__, exc)

        # Try fallback
        try:
            return self._fallback.get(model_id, filename)
        except Exception as exc:
            logger.warning("Fallback GET failed: %s", exc)

        # Try local mirror
        try:
            return self._mirror.get(model_id, filename)
        except Exception as exc:
            raise FileNotFoundError(
                f"Artifact {model_id}/{filename} not found in any backend"
            ) from exc

    def _list_with_fallback(self, model_id: str) -> List[str]:
        for backend in (self._primary, self._fallback, self._mirror):
            try:
                files = backend.list_files(model_id)
                if files:
                    return files
            except Exception:
                continue
        return []
