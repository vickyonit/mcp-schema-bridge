"""release-please config: paths it accepts, and every versioned file kept in lockstep."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = json.loads((ROOT / "release-please-config.json").read_text())
MANIFEST = json.loads((ROOT / ".release-please-manifest.json").read_text())


def _paths() -> list[str]:
    out: list[str] = []
    for path, pkg in CONFIG["packages"].items():
        out.append(path)
        out += [pkg.get("changelog-path", ""), pkg.get("version-file", "")]
        out += [f["path"] for f in pkg.get("extra-files", [])]
    return [p for p in out if p]


def test_release_please_paths_stay_inside_the_repo() -> None:
    # release-please rejects "illegal pathing characters" such as "../".
    assert not [p for p in _paths() if ".." in p]


def test_single_root_package_releases_both_languages() -> None:
    assert list(CONFIG["packages"]) == ["."]
    extra = {f["path"] for f in CONFIG["packages"]["."]["extra-files"]}
    assert extra == {
        "python/src/mcp_schema_bridge/_version.py",
        "typescript/package.json",
        "typescript/src/core/version.ts",
    }


def test_versioned_files_match_the_manifest() -> None:
    v = MANIFEST["."]
    assert (ROOT / "version.txt").read_text().strip() == v
    py = (ROOT / "python/src/mcp_schema_bridge/_version.py").read_text()
    assert re.search(rf'__version__ = "{re.escape(v)}"  # x-release-please-version', py)
    assert json.loads((ROOT / "typescript/package.json").read_text())["version"] == v
    ts = (ROOT / "typescript/src/core/version.ts").read_text()
    assert f'"{v}"; // x-release-please-version' in ts
