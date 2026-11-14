import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.unit.test_lexicon_release import sources, verify_archive


def command(args: list[str], cwd: Path, env: dict[str, str] | None = None) -> str:
    return subprocess.check_output(args, cwd=cwd, env=env, text=True, stderr=subprocess.STDOUT)


def test_real_dispatch_from_main_and_linked_worktree_offline(tmp_path: Path) -> None:
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        pytest.skip("PowerShell 7 is needed for dev.ps1 command acceptance")
    repo = Path(__file__).parents[3]
    main = tmp_path / "main fixture"
    linked = tmp_path / "linked fixture"
    main.mkdir()
    scripts = main / "scripts"
    scripts.mkdir()
    for name in ("dev.ps1", "setup.ps1", "lexicon.ps1"):
        shutil.copyfile(repo / "scripts" / name, scripts / name)
    shutil.copytree(
        repo / "backend" / "scripts",
        main / "backend" / "scripts",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    (main / ".env.example").write_text("", encoding="utf-8")
    command(["git", "init", "--quiet", "--template="], main)
    command(["git", "add", "scripts", "backend", ".env.example"], main)
    command(
        [
            "git",
            "-c",
            "user.name=Lexicon Test",
            "-c",
            "user.email=lexicon@example.invalid",
            "-c",
            f"core.hooksPath={tmp_path / 'no-hooks'}",
            "commit",
            "--quiet",
            "--no-gpg-sign",
            "-m",
            "synthetic fixture",
        ],
        main,
    )
    command(["git", "worktree", "add", "--quiet", "--detach", str(linked)], main)
    raw = main / "data" / "lexicon" / "raw"
    manifest = sources(raw)
    bootstrap = tmp_path / "offline.py"
    bootstrap.write_text(
        """import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from dataclasses import replace
import httpx
from scripts.lexicon_sources import SOURCES
SOURCES["oewn"] = replace(SOURCES["oewn"], sha256=sys.argv.pop(1))
native = httpx.AsyncClient
def deny(request):
    raise AssertionError(f"offline command attempted network: {request.url}")
httpx.AsyncClient = lambda **kwargs: native(transport=httpx.MockTransport(deny), **kwargs)
from scripts.lexicon_release import main
main()
""",
        encoding="utf-8",
    )
    driver = tmp_path / "invoke.ps1"
    driver.write_text(
        """$ErrorActionPreference = 'Stop'
function uv {
    $forward = @($args | Select-Object -Skip 5)
    & $env:LEXICON_TEST_PYTHON $env:LEXICON_TEST_BOOTSTRAP $env:LEXICON_TEST_PIN @forward
    $global:LASTEXITCODE = $LASTEXITCODE
}
$entrypoint = $args[0]
$forward = @($args | Select-Object -Skip 1)
& $entrypoint @forward
""",
        encoding="utf-8",
    )
    env = {
        **os.environ,
        "PYTHONPATH": str(repo / "backend"),
        "LEXICON_TEST_PYTHON": sys.executable,
        "LEXICON_TEST_BOOTSTRAP": str(bootstrap),
        "LEXICON_TEST_PIN": manifest["artifacts"]["oewn"]["sha256"],
    }

    def invoke(root: Path, day: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                pwsh,
                "-NoProfile",
                "-File",
                str(driver),
                str(root / "scripts" / "dev.ps1"),
                "lexicon",
                "-Date",
                day,
            ],
            cwd=root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

    try:
        for root, day in ((main, "2026-11-14"), (linked, "2026-11-15")):
            result = invoke(root, day)
            assert result.returncode == 0, result.stdout
            verify_archive(
                main / "dist" / f"pandawords-lexicon-{day}.tar.gz", tmp_path / f"unpacked-{day}"
            )
        assert not (linked / "data").exists()
        assert not (linked / "dist").exists()
        assert (main / "data" / "lexicon" / "lexicon.sqlite").is_file()
        result = invoke(linked, "2026-11-14")
        assert result.returncode != 0
        assert "lexicon prepare failed: output already exists" in result.stdout
        (raw / "kaikki-english.jsonl").write_text("mismatch", encoding="utf-8")
        result = invoke(linked, "2026-11-16")
        assert result.returncode != 0
        assert "lexicon download:kaikki failed:" in result.stdout
        assert not (main / "dist" / "pandawords-lexicon-2026-11-16.tar.gz").exists()
        assert json.loads((raw / "manifest.json").read_text()) == manifest
    finally:
        command(["git", "worktree", "remove", "--force", str(linked)], main)
