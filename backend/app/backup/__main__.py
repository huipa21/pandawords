from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import app.backup as package
from app.backup.schedule import run_schedule
from app.core.config import Settings
from app.core.logging import configure_logging
from app.domain.site_backup import SiteBackupError
from app.services.site_backup import create_backup
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
    try:
        print(asyncio.run(_run(args, settings)))
    except SiteBackupError as error:
        print(f"FAILED at stage '{error.stage}': {error.message}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    except Exception as error:
        print(f"FAILED with unexpected {type(error).__name__}; see logs.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
