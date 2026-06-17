#!/usr/bin/env python3
"""
Tests for predose.py remove and implantation (backport) functionality
using data files from tests/predose/data/

These tests assert the CORRECT intended behavior. They fail because
predose.py contains bugs:
1. predose.py:256-262 -- remove() checks if (name, '') in self.packages
   but packages are keyed by (name, version), so removing by bare name
   always fails (should resolve to latest version first).
2. predose.py:414-427 -- _parse_input_line() resolves bare names to
   latest version but run() never calls it; always creates (name, ''),
   so backport by bare name always fails.
3. predose.py:265-278 -- backport() adds new (name, version2) without
   removing old (name, version1), creating duplicates on version change.
"""

import pytest
import sys
import os
import subprocess
import tempfile
import re
from pathlib import Path


def find_predose_script():
    current_dir = Path(__file__).parent
    possible_paths = [
        current_dir.parent.parent / "predose" / "predose.py",
        current_dir.parent / "predose.py",
        current_dir.parent.parent / "predose.py",
        Path.cwd() / "predose" / "predose.py",
        Path.cwd() / "predose.py",
        Path.cwd().parent / "predose" / "predose.py",
    ]
    for path in possible_paths:
        if path.exists():
            return str(path)
    for parent in [current_dir] + list(current_dir.parents):
        script_path = parent / "predose" / "predose.py"
        if script_path.exists():
            return str(script_path)
        script_path = parent / "predose.py"
        if script_path.exists():
            return str(script_path)
    return None


PREDOSE_SCRIPT = find_predose_script()
PROJECT_ROOT = Path(PREDOSE_SCRIPT).parent.parent if PREDOSE_SCRIPT else None

if PREDOSE_SCRIPT is None:
    pytest.skip("predose.py not found in expected locations", allow_module_level=True)

DATA_DIR = Path(__file__).parent / "data"


def run_predose(positional, extra_args, input_data=""):
    if PREDOSE_SCRIPT is None:
        pytest.skip("predose.py not found")

    env = os.environ.copy()
    if PROJECT_ROOT:
        pythonpath = env.get("PYTHONPATH", "")
        if pythonpath:
            env["PYTHONPATH"] = f"{PROJECT_ROOT}:{pythonpath}"
        else:
            env["PYTHONPATH"] = str(PROJECT_ROOT)

    cmd = [sys.executable, PREDOSE_SCRIPT] + [str(p) for p in positional] + extra_args

    result = subprocess.run(
        cmd,
        input=input_data,
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT) if PROJECT_ROOT else None,
        env=env,
        timeout=30,
    )

    if result.returncode != 0:
        print(f"\nCommand: {' '.join(cmd)}")
        print(f"PYTHONPATH: {env.get('PYTHONPATH', 'Not set')}")
        print(f"Working directory: {PROJECT_ROOT}")
        print(f"STDERR: {result.stderr}")
        print(f"STDOUT: {result.stdout}")

    return result


def count_packages_in_output(output):
    blocks = [b for b in output.strip().split("\n\n") if b.strip()]
    return len(blocks)


def count_packages_in_file(path):
    content = Path(path).read_text()
    return count_packages_in_output(content)


def get_package_names_in_output(output):
    names = []
    for block in output.strip().split("\n\n"):
        for line in block.split("\n"):
            if line.startswith("Package: "):
                names.append(line[len("Package: "):])
                break
    return names


@pytest.fixture
def temp_sample_packages():
    src = DATA_DIR / "sample_Packages"
    with tempfile.NamedTemporaryFile(mode="w", suffix="_Packages", delete=False) as f:
        f.write(src.read_text())
        temp_path = f.name
    yield Path(temp_path)
    os.unlink(temp_path)


@pytest.fixture
def temp_new_packages():
    src = DATA_DIR / "new_Packages"
    with tempfile.NamedTemporaryFile(mode="w", suffix="_Packages", delete=False) as f:
        f.write(src.read_text())
        temp_path = f.name
    yield Path(temp_path)
    os.unlink(temp_path)


@pytest.fixture
def temp_sample_sources():
    src = DATA_DIR / "sample_Sources"
    with tempfile.NamedTemporaryFile(mode="w", suffix="_Sources", delete=False) as f:
        f.write(src.read_text())
        temp_path = f.name
    yield Path(temp_path)
    os.unlink(temp_path)


@pytest.fixture
def temp_new_sources():
    src = DATA_DIR / "new_Sources"
    with tempfile.NamedTemporaryFile(mode="w", suffix="_Sources", delete=False) as f:
        f.write(src.read_text())
        temp_path = f.name
    yield Path(temp_path)
    os.unlink(temp_path)


def _get_remove_output(repo_path, input_data, extra_flags=None):
    flags = ["--remove"]
    if extra_flags:
        flags.extend(extra_flags)
    result = run_predose([repo_path], flags, input_data=input_data)
    assert result.returncode == 0, f"Error: {result.stderr}"
    return result.stdout


def _get_backport_output(origin_path, target_path, input_data):
    result = run_predose([origin_path, target_path], [], input_data=input_data)
    assert result.returncode == 0, f"Error: {result.stderr}"
    return result.stdout


# ============================================================
# TEST 1: Remove from sample_Packages
# 10 packages: 7 with version=format, 3 without version
# Correct behavior: bare names resolve to latest version and get removed.
# ============================================================

REMOVE_WITH_VERSION = """\
0ad=0.27.0-2+b1
0ad-data=0.27.0-1
0xffff=0.9-1+b1
2048=1.0.3-1
2ping=4.5-1.2
2vcard=0.6-5
3dchess=0.8.1-23
"""

REMOVE_WITHOUT_VERSION = """\
0ad-data-common
7kaa
a2ps
"""

REMOVE_ALL_10 = REMOVE_WITH_VERSION + REMOVE_WITHOUT_VERSION


def test_remove_7_with_version_succeeds(temp_sample_packages):
    """Remove 7 packages with explicit version. These should succeed."""
    original_count = count_packages_in_output(
        _get_remove_output(temp_sample_packages, "", extra_flags=["--latest"])
    )
    output = _get_remove_output(temp_sample_packages, REMOVE_WITH_VERSION, extra_flags=["--latest"])
    remaining_count = count_packages_in_output(output)
    assert remaining_count == original_count - 7, (
        f"Expected {original_count - 7} packages remaining, got {remaining_count}"
    )
    remaining_names = get_package_names_in_output(output)
    for name in ["0ad", "0ad-data", "0xffff", "2048", "2ping", "2vcard", "3dchess"]:
        assert name not in remaining_names, (
            f"Package '{name}' should have been removed"
        )


def test_remove_3_without_version_removes_latest(temp_sample_packages):
    """Remove 3 packages WITHOUT version.
    CORRECT behavior: each bare name should resolve to its latest version
    and be removed. KNOWN BUG: (name, '') never matches self.packages keys."""
    original_count = count_packages_in_file(temp_sample_packages)
    output = _get_remove_output(temp_sample_packages, REMOVE_WITHOUT_VERSION)
    remaining_count = count_packages_in_output(output)
    assert remaining_count == original_count - 3, (
        f"FAIL (bug #1): Expected {original_count - 3} packages remaining "
        f"(3 bare names resolved to latest and removed), "
        f"got {remaining_count}. predose.py does not resolve bare names."
    )
    remaining_names = get_package_names_in_output(output)
    for name in ["0ad-data-common", "7kaa", "a2ps"]:
        assert name not in remaining_names, (
            f"Package '{name}' should have been removed"
        )


def test_remove_10_mixed_removes_all(temp_sample_packages):
    """Remove 10 packets (7 with version, 3 without).
    CORRECT behavior: all 10 should be removed (bare names resolved)."""
    original_count = count_packages_in_file(temp_sample_packages)
    output = _get_remove_output(temp_sample_packages, REMOVE_ALL_10)
    remaining_count = count_packages_in_output(output)
    expected = original_count - 10
    assert remaining_count == expected, (
        f"FAIL (bug #1): Expected {expected} packages remaining (all 10 removed), "
        f"got {remaining_count}. Only 7 with explicit version were removed."
    )


# ============================================================
# TEST 2: Remove with --latest option
# Same inputs, but --latest first prunes to latest versions only.
# ============================================================


def test_remove_with_latest_7_with_version(temp_sample_packages):
    """Remove 7 with version + --latest. Works because explicit version."""
    original_count = count_packages_in_output(
        _get_remove_output(temp_sample_packages, "", extra_flags=["--latest"])
    )
    output = _get_remove_output(temp_sample_packages, REMOVE_WITH_VERSION, extra_flags=["--latest"])
    remaining_count = count_packages_in_output(output)
    assert remaining_count == original_count - 7, (
        f"Expected {original_count - 7} packages, got {remaining_count}"
    )
    remaining_names = get_package_names_in_output(output)
    for name in ["0ad", "0ad-data", "0xffff", "2048", "2ping", "2vcard", "3dchess"]:
        assert name not in remaining_names
    assert len(remaining_names) == len(set(remaining_names))


def test_remove_with_latest_3_without_version(temp_sample_packages):
    """Remove 3 without version + --latest.
    CORRECT: bare names resolve to latest and get removed."""
    original_count = count_packages_in_output(
        _get_remove_output(temp_sample_packages, "", extra_flags=["--latest"])
    )
    output = _get_remove_output(temp_sample_packages, REMOVE_WITHOUT_VERSION, extra_flags=["--latest"])
    remaining_count = count_packages_in_output(output)
    assert remaining_count == original_count - 3, (
        f"FAIL (bug #1): Expected {original_count - 3} packages remaining, "
        f"got {remaining_count}. Bare names not resolved."
    )


# ============================================================
# TEST 3: Implantation from new_Packages to sample_Packages
# new_Packages has: vim, vim-common, 0xffff, 2048, 0ad (newer), 0ad-data (newer)
# ============================================================

BACKPORT_PACKAGES_WITH_VERSION = """\
0ad=0.28.0-3+b2
0ad-data=0.28.0-1
vim=2:9.2.0461-1
vim-common=2:9.2.0461-1
2048=1.0.3-1
"""


def test_backport_5_with_version_no_duplicates(temp_new_packages, temp_sample_packages):
    """Implant 5 packages with explicit version.
    vim/vim-common/0ad/0ad-data are new with version (+4).
    2048 replaces existing (+0)."""
    original_count = count_packages_in_file(temp_sample_packages)
    output = _get_backport_output(temp_new_packages, temp_sample_packages,
                                  BACKPORT_PACKAGES_WITH_VERSION)
    remaining_count = count_packages_in_output(output)
    expected = original_count + 4  # only vim and vim-common are new
    assert remaining_count == expected
    remaining_names = get_package_names_in_output(output)
    assert "vim" in remaining_names
    assert "vim-common" in remaining_names
    assert "0ad" in remaining_names
    assert "0ad-data" in remaining_names


def test_backport_without_version_resolves_latest(temp_new_packages, temp_sample_packages):
    """Implant packages without version.
    CORRECT: bare names resolve to latest version in origin and get backported."""
    original_count = count_packages_in_file(temp_sample_packages)
    input_data = "0ad\nvim\n0xffff\n2048\n"
    output = _get_backport_output(temp_new_packages, temp_sample_packages, input_data)
    remaining_count = count_packages_in_output(output)
    assert remaining_count > original_count, (
        f"FAIL (bug #2): Expected packages to be added (bare names should resolve "
        f"to latest versions), got {remaining_count} (same as original {original_count}). "
        f"_parse_input_line() exists but run() never calls it."
    )


def test_backport_mixed_no_duplicates(temp_new_packages, temp_sample_packages):
    """Implant mix of with/without version. No duplicates should appear."""
    original_count = count_packages_in_file(temp_sample_packages)
    input_data = (
        "0ad=0.28.0-3+b2\n"
        "vim=2:9.2.0461-1\n"
        "vim-common\n"
        "0ad-data=0.28.0-1\n"
        "2048\n"
        "0xffff=0.9-1+b1\n"
    )
    output = _get_backport_output(temp_new_packages, temp_sample_packages, input_data)
    remaining_names = get_package_names_in_output(output)
    assert "vim" in remaining_names
    # vim-common and 2048 should have been resolved and added/replaced if version differs
    assert "vim-common" in remaining_names, (
        f"FAIL (bug #2): 'vim-common' (bare name) should resolve and be added"
    )
    # No duplicates
    for name in ["vim", "2048"]:
        pattern = re.compile(rf'^Package: {re.escape(name)}$', re.MULTILINE)
        assert len(pattern.findall(output)) == 1, (
            f"FAIL (bug #3): Package '{name}' appears as duplicate via backport"
        )


# ============================================================
# TEST 4: Implantation from new_Sources to sample_Sources
# ============================================================

BACKPORT_SOURCES = """\
vim=2:9.2.0461-1
vim-addon-manager=0.5.11
vim-addon-mw-utils=0.2-6
"""


def test_backport_sources_with_version(temp_new_sources, temp_sample_sources):
    """Implant 3 new source packages with version."""
    original_count = count_packages_in_file(temp_sample_sources)
    output = _get_backport_output(temp_new_sources, temp_sample_sources, BACKPORT_SOURCES)
    remaining_count = count_packages_in_output(output)
    expected = original_count + 3
    assert remaining_count == expected, (
        f"Expected {expected} packages after backport (3 new), "
        f"got {remaining_count}"
    )
    remaining_names = get_package_names_in_output(output)
    for name in ["vim", "vim-addon-manager", "vim-addon-mw-utils"]:
        assert name in remaining_names, f"Source '{name}' should have been added"


def test_backport_sources_without_version_resolves(temp_new_sources, temp_sample_sources):
    """Implant source packages without version.
    CORRECT: bare names resolve to latest version."""
    original_count = count_packages_in_file(temp_sample_sources)
    output = _get_backport_output(temp_new_sources, temp_sample_sources,
                                  "vim\nvim-addon-manager\nvim-addon-mw-utils\n")
    remaining_count = count_packages_in_output(output)
    assert remaining_count == original_count


def test_backport_sources_duplicate_version_no_growth(temp_new_sources, temp_sample_sources):
    """Re-implanting same package should not increase count."""
    output1 = _get_backport_output(temp_new_sources, temp_sample_sources,
                                   "vim=2:9.2.0461-1\n")
    count1 = count_packages_in_output(output1)
    output2 = _get_backport_output(temp_new_sources, temp_sample_sources,
                                   "vim=2:9.2.0461-1\n")
    count2 = count_packages_in_output(output2)
    assert count1 == count2, (
        f"Re-implanting same package should not create duplicate. "
        f"Counts: {count1} -> {count2}"
    )


# ============================================================
# Verify data files exist
# ============================================================


def test_data_files_exist():
    assert DATA_DIR.exists(), f"Data directory not found: {DATA_DIR}"
    for f in ["sample_Packages", "sample_Sources", "new_Packages", "new_Sources"]:
        path = DATA_DIR / f
        assert path.exists(), f"Data file not found: {path}"
        assert len(path.read_text()) > 0, f"Data file is empty: {path}"


def test_script_found():
    assert PREDOSE_SCRIPT is not None, "predose.py not found"
    assert Path(PREDOSE_SCRIPT).exists()
