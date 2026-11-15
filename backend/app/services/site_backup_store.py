"""Permission-restricted site backup directory: lock, atomic publish, listing, retention."""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import structlog

from app.domain.site_backup import SiteBackupError, SiteBackupRead, backup_in_progress

NAME = re.compile(r"^site-(\d{8}T\d{12})Z\.tar\.gz$")
LOCK = ".site-backup.lock"
WORK_PREFIX = ".work-"
_SIDECAR = ".sha256"


def prepare_directory(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(directory, 0o700)
    return directory


def restrict(path: Path) -> None:
    os.chmod(path, 0o700 if path.is_dir() else 0o600)


def new_name(now: datetime) -> str:
    return f"site-{now.astimezone(UTC):%Y%m%dT%H%M%S%f}Z.tar.gz"


def sidecar(path: Path) -> Path:
    return path.with_name(path.name + _SIDECAR)


class BackupLock:
    """Cross-process exclusive lock (API and `backup` service share the volume)."""

    def __init__(self, directory: Path, stale_seconds: int) -> None:
        self.path = directory / LOCK
        self.stale_seconds = stale_seconds
        self.token = uuid4().hex
        self.held = False

    def acquire(self) -> BackupLock:
        prepare_directory(self.path.parent)
        payload = json.dumps(
            {"token": self.token, "pid": os.getpid(), "host": socket.gethostname()}
        ).encode()
        for _ in range(2):
            try:
                descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                if not self._remove_stale():
                    raise backup_in_progress() from None
                continue
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
            self.held = True
            return self
        raise backup_in_progress()

    def _remove_stale(self) -> bool:
        try:
            age = time.time() - self.path.stat().st_mtime
        except FileNotFoundError:
            return True
        if age < self.stale_seconds:
            return False
        structlog.get_logger().warning("site_backup_stale_lock_removed", age_seconds=int(age))
        self.path.unlink(missing_ok=True)
        return True

    def release(self) -> None:
        if not self.held:
            return
        self.held = False
        try:
            if json.loads(self.path.read_bytes()).get("token") == self.token:
                self.path.unlink()
        except OSError, ValueError:
            structlog.get_logger().warning("site_backup_lock_release_failed")


def clean_incomplete(directory: Path) -> None:
    """Only call while holding the lock: anything unpublished is a crashed attempt."""
    for entry in directory.iterdir():
        name = entry.name
        if name.startswith(WORK_PREFIX) and entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry, ignore_errors=True)
        elif name.endswith(".partial") and NAME.match(name.removesuffix(".partial")):
            entry.unlink(missing_ok=True)
        elif name.endswith(_SIDECAR) and NAME.match(name.removesuffix(_SIDECAR)):
            if not directory.joinpath(name.removesuffix(_SIDECAR)).is_file():
                entry.unlink(missing_ok=True)


def _read(path: Path) -> SiteBackupRead | None:
    match = NAME.match(path.name)
    marker = sidecar(path)
    if match is None or path.is_symlink() or not path.is_file() or not marker.is_file():
        return None
    digest = marker.read_text("ascii", errors="replace").split(" ", 1)[0].strip()
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        return None
    created = datetime.strptime(match.group(1), "%Y%m%dT%H%M%S%f").replace(tzinfo=UTC)
    return SiteBackupRead(
        name=path.name, created_at=created, size=path.stat().st_size, sha256=digest
    )


def list_backups(directory: Path) -> list[SiteBackupRead]:
    if not directory.is_dir():
        return []
    found = [item for path in directory.iterdir() if (item := _read(path)) is not None]
    return sorted(found, key=lambda item: item.name, reverse=True)


def resolve(directory: Path, name: str) -> Path:
    if NAME.fullmatch(name) is None:
        raise SiteBackupError("not_found", "Site backup not found.", 404)
    path = directory / name
    if _read(path) is None:
        raise SiteBackupError("not_found", "Site backup not found.", 404)
    return path


def publish(partial: Path, final: Path, digest: str) -> None:
    """Sidecar first, then an atomic rename: listings only ever see complete archives."""
    if final.exists():
        raise SiteBackupError("publish", "A backup with this name already exists.")
    marker = sidecar(final)
    temporary = marker.with_name(marker.name + ".partial")
    temporary.write_text(f"{digest}  {final.name}\n", "ascii")
    restrict(temporary)
    os.replace(temporary, marker)
    restrict(partial)
    os.replace(partial, final)


def apply_retention(directory: Path, keep: int) -> list[str]:
    removed: list[str] = []
    for backup in list_backups(directory)[keep:]:
        path = directory / backup.name
        path.unlink(missing_ok=True)
        sidecar(path).unlink(missing_ok=True)
        removed.append(backup.name)
    return removed
