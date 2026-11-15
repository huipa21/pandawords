from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from uuid import uuid4

import app.backup as package
from app.backup.schedule import run_schedule
from app.core.config import Settings
from app.core.logging import configure_logging
from app.domain.site_backup import SiteBackupError
from app.services.site_backup import create_backup
from app.services.site_backup_store import prepare_directory, restrict
from app.services.site_restore import preflight, restore_site


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.backup",
        description=package.__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("schedule", help="run daily backups (default)")
    commands.add_parser("once", help="create one site backup now")
    check = commands.add_parser("check", help="verify an archive; changes nothing")
    check.add_argument("archive", type=Path)
    restore = commands.add_parser("restore", help="restore an archive (stop api/worker first)")
    restore.add_argument("archive", type=Path)
    restore.add_argument(
        "--replace",
        action="store_true",
        help="export then replace a non-empty target database",
    )
    return parser


def _receive(settings: Settings, value: Path) -> Path | None:
    """`-` streams the archive on stdin (restore.sh), avoiding host file permission issues."""
    if str(value) != "-":
        return None
    directory = prepare_directory(settings.site_backup_dir)
    target = directory / f".upload-{uuid4().hex}.tar.gz"
    received = 0
    try:
        with target.open("xb") as output:
            while chunk := sys.stdin.buffer.read(1024 * 1024):
                received += len(chunk)
                if received > settings.site_backup_max_bytes:
                    raise SiteBackupError("preflight", "Archive exceeds SITE_BACKUP_MAX_BYTES.")
                output.write(chunk)
        restrict(target)
    except OSError as error:
        target.unlink(missing_ok=True)
        message = f"Could not receive the archive: {type(error).__name__}"
        raise SiteBackupError("preflight", message) from None
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return target


async def _run(args: argparse.Namespace, settings: Settings) -> str:
    match args.command:
        case "once":
            created = await create_backup(settings, "manual")
            return f"Site backup created: {created.name} ({created.size} bytes)"
        case "check":
            manifest = await preflight(settings, args.archive)
            return (
                f"Archive OK: created {manifest.created_at.isoformat()}, "
                f"{len(manifest.database.tables)} tables, {len(manifest.media)} media files"
            )
        case "restore":
            result = await restore_site(settings, args.archive, replace=args.replace)
            return "Restore verified: " + result.model_dump_json()
        case _:
            await run_schedule(settings)
            return "Scheduler stopped"


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = Settings()
    configure_logging(settings.app_env)
    received: Path | None = None
    try:
        if args.command in {"check", "restore"}:
            received = _receive(settings, args.archive)
            args.archive = received or args.archive
        print(asyncio.run(_run(args, settings)))
    except SiteBackupError as error:
        print(f"FAILED at stage '{error.stage}': {error.message}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    except Exception as error:
        print(f"FAILED with unexpected {type(error).__name__}; see logs.", file=sys.stderr)
        return 1
    finally:
        if received is not None:
            received.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
