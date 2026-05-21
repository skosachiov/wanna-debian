#!/usr/bin/env python3
"""
Tests for predose.py --resolve-bin functionality
"""

import pytest
import sys
import os
import subprocess
from pathlib import Path

# Find the predose.py script
def find_predose_script():
    """Find predose.py in the project structure"""
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

# Skip all tests if predose.py is not found
if PREDOSE_SCRIPT is None:
    pytest.skip("predose.py not found in expected locations", allow_module_level=True)


# Sample package data for testing (mimicking Debian/Ubuntu Packages format)
# This includes packages with multiple binary packages from same source
SAMPLE_PACKAGES_CONTENT = """\
Package: vim-common
Version: 2:8.2.3995-1ubuntu2.1
Source: vim
Depends: vim-tiny (>= 2:8.2.3995-1ubuntu2.1) | vim (>= 2:8.2.3995-1ubuntu2.1), libc6 (>= 2.34)

Package: vim-tiny
Version: 2:8.2.3995-1ubuntu2.1
Source: vim
Depends: libc6 (>= 2.34)

Package: vim
Version: 2:8.2.3995-1ubuntu2.1
Source: vim
Depends: vim-common (= 2:8.2.3995-1ubuntu2.1), libacl1 (>= 2.2.23), libc6 (>= 2.34), libgpm2 (>= 1.20.7), libselinux1 (>= 3.1), libsodium23 (>= 1.0.14), libtinfo6 (>= 6)

Package: nano
Version: 6.2-1
Source: nano
Depends: libc6 (>= 2.34), libncursesw6 (>= 6), libtinfo6 (>= 6)

Package: curl
Version: 7.81.0-1ubuntu1.15
Source: curl
Depends: libc6 (>= 2.34), libcurl4 (= 7.81.0-1ubuntu1.15)

Package: libcurl4
Version: 7.81.0-1ubuntu1.15
Source: curl
Depends: libc6 (>= 2.34), libnghttp2-14 (>= 1.40.0), libpsl5 (>= 0.20.0), librtmp1 (>= 2.4+), libssh2-1 (>= 1.7.0), libssl3 (>= 3.0.0), zlib1g (>= 1:1.1.4)

Package: wget
Version: 1.21.2-2ubuntu1
Source: wget
Depends: libc6 (>= 2.34), libssl3 (>= 3.0.0)

Package: git
Version: 1:2.34.1-1ubuntu1.10
Source: git
Depends: libc6 (>= 2.34), libcurl3-gnutls (>= 7.16.2), libpcre2-8-0 (>= 10.34), zlib1g (>= 1:1.1.4)

Package: git-man
Version: 1:2.34.1-1ubuntu1.10
Source: git
Depends: git (>> 1:2.34.1-1ubuntu1.10)

Package: python3
Version: 3.10.12-1~22.04.3
Source: python3-defaults
Depends: python3.10 (>= 3.10.12-1~22.04.3), libpython3-stdlib (= 3.10.12-1~22.04.3)

Package: python3.10
Version: 3.10.12-1~22.04.3
Source: python3.10
Depends: libc6 (>= 2.34), libssl3 (>= 3.0.0)

Package: build-essential
Version: 12.9ubuntu3
Source: build-essential
Depends: gcc (>= 4:11.2), g++ (>= 4:11.2), make, dpkg-dev

Package: gcc
Version: 4:11.2.0-1ubuntu1
Source: gcc-defaults
Depends: cpp (= 4:11.2.0-1ubuntu1), gcc-11 (>= 11.2.0-1~)

Package: g++
Version: 4:11.2.0-1ubuntu1
Source: gcc-defaults
Depends: g++-11 (>= 11.2.0-1~), gcc (= 4:11.2.0-1ubuntu1)
"""


@pytest.fixture
def sample_packages_file(tmp_path):
    """Create a temporary Packages file with sample data"""
    packages_file = tmp_path / "sample_Packages"
    packages_file.write_text(SAMPLE_PACKAGES_CONTENT)
    return str(packages_file)


def run_predose(packages_file, args, input_data=""):
    """Helper function to run predose.py with given arguments and input"""
    if PREDOSE_SCRIPT is None:
        pytest.skip("predose.py not found")

    # Set PYTHONPATH to include the project root so toposort can be found
    env = os.environ.copy()
    if PROJECT_ROOT:
        pythonpath = env.get('PYTHONPATH', '')
        if pythonpath:
            env['PYTHONPATH'] = f"{PROJECT_ROOT}:{pythonpath}"
        else:
            env['PYTHONPATH'] = str(PROJECT_ROOT)

    cmd = [sys.executable, PREDOSE_SCRIPT, packages_file] + args

    result = subprocess.run(
        cmd,
        input=input_data,
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT) if PROJECT_ROOT else None,
        env=env
    )

    # Print stderr for debugging if test fails
    if result.returncode != 0:
        print(f"\nCommand: {' '.join(cmd)}")
        print(f"PYTHONPATH: {env.get('PYTHONPATH', 'Not set')}")
        print(f"Working directory: {PROJECT_ROOT}")
        print(f"STDERR: {result.stderr}")
        print(f"STDOUT: {result.stdout}")

    return result


def test_resolve_bin_vim_to_binaries(sample_packages_file):
    """Test resolving vim source package to its binary packages"""
    result = run_predose(sample_packages_file, ['--resolve-bin'], "vim\n")

    assert result.returncode == 0, f"Error: {result.stderr}"
    output_lines = sorted(result.stdout.strip().split('\n'))

    # vim source produces: vim-common, vim-tiny, vim
    expected = sorted(["vim-common", "vim-tiny", "vim"])
    assert output_lines == expected, f"Expected {expected}, got {output_lines}"


def test_resolve_bin_curl_to_binaries(sample_packages_file):
    """Test resolving curl source package to its binary packages"""
    result = run_predose(sample_packages_file, ['--resolve-bin'], "curl\n")

    assert result.returncode == 0, f"Error: {result.stderr}"
    output_lines = sorted(result.stdout.strip().split('\n'))

    # curl source produces: curl, libcurl4
    expected = sorted(["curl", "libcurl4"])
    assert output_lines == expected, f"Expected {expected}, got {output_lines}"


def test_resolve_bin_git_to_binaries(sample_packages_file):
    """Test resolving git source package to its binary packages"""
    result = run_predose(sample_packages_file, ['--resolve-bin'], "git\n")

    assert result.returncode == 0, f"Error: {result.stderr}"
    output_lines = sorted(result.stdout.strip().split('\n'))

    # git source produces: git, git-man
    expected = sorted(["git", "git-man"])
    assert output_lines == expected, f"Expected {expected}, got {output_lines}"


def test_resolve_bin_nano_to_binaries(sample_packages_file):
    """Test resolving nano source package to its binary packages"""
    result = run_predose(sample_packages_file, ['--resolve-bin'], "nano\n")

    assert result.returncode == 0, f"Error: {result.stderr}"
    output_lines = result.stdout.strip().split('\n')

    # nano source produces just: nano
    assert output_lines == ["nano"], f"Expected ['nano'], got {output_lines}"


def test_resolve_bin_wget_to_binaries(sample_packages_file):
    """Test resolving wget source package to its binary packages"""
    result = run_predose(sample_packages_file, ['--resolve-bin'], "wget\n")

    assert result.returncode == 0, f"Error: {result.stderr}"
    output_lines = result.stdout.strip().split('\n')

    # wget source produces just: wget
    assert output_lines == ["wget"], f"Expected ['wget'], got {output_lines}"


def test_resolve_bin_python3_to_binaries(sample_packages_file):
    """Test resolving python3-defaults source package to its binary packages"""
    result = run_predose(sample_packages_file, ['--resolve-bin'], "python3-defaults\n")

    assert result.returncode == 0, f"Error: {result.stderr}"
    output_lines = result.stdout.strip().split('\n')

    # python3-defaults source produces: python3
    assert output_lines == ["python3"], f"Expected ['python3'], got {output_lines}"


def test_resolve_bin_python3_10_to_binaries(sample_packages_file):
    """Test resolving python3.10 source package to its binary packages"""
    result = run_predose(sample_packages_file, ['--resolve-bin'], "python3.10\n")

    assert result.returncode == 0, f"Error: {result.stderr}"
    output_lines = result.stdout.strip().split('\n')

    # python3.10 source produces: python3.10
    assert output_lines == ["python3.10"], f"Expected ['python3.10'], got {output_lines}"


def test_resolve_bin_gcc_defaults_to_binaries(sample_packages_file):
    """Test resolving gcc-defaults source package to its binary packages"""
    result = run_predose(sample_packages_file, ['--resolve-bin'], "gcc-defaults\n")

    assert result.returncode == 0, f"Error: {result.stderr}"
    output_lines = sorted(result.stdout.strip().split('\n'))

    # gcc-defaults source produces: gcc, g++
    expected = sorted(["gcc", "g++"])
    assert output_lines == expected, f"Expected {expected}, got {output_lines}"


def test_resolve_bin_multiple_sources(sample_packages_file):
    """Test resolving multiple source packages to their binary packages"""
    input_data = "vim\ncurl\ngit\n"
    result = run_predose(sample_packages_file, ['--resolve-bin'], input_data)

    assert result.returncode == 0, f"Error: {result.stderr}"

    output_lines = sorted(result.stdout.strip().split('\n'))

    # Check each group's binaries
    assert sorted(output_lines) == sorted(["vim-common", "vim-tiny", "vim", "curl", "libcurl4", "git", "git-man"])

def test_resolve_bin_with_version(sample_packages_file):
    """Test resolving source to binary packages with version information"""
    result = run_predose(sample_packages_file, ['--resolve-bin', '--add-version'], "vim\n")

    assert result.returncode == 0, f"Error: {result.stderr}"
    output_lines = sorted(result.stdout.strip().split('\n'))

    # Should include version in format: pkg=version
    expected = sorted([
        "vim-common=2:8.2.3995-1ubuntu2.1",
        "vim-tiny=2:8.2.3995-1ubuntu2.1",
        "vim=2:8.2.3995-1ubuntu2.1"
    ])
    assert output_lines == expected, f"Expected {expected}, got {output_lines}"


def test_resolve_bin_nonexistent_source(sample_packages_file):
    """Test resolving a source package that doesn't exist"""
    result = run_predose(sample_packages_file, ['--resolve-bin'], "nonexistent-source\n")

    assert result.returncode == 0, f"Error: {result.stderr}"
    output = result.stdout.strip()

    # Should output nothing for unresolved source
    assert output == "", f"Expected empty output, got '{output}'"


def test_resolve_bin_binary_as_input(sample_packages_file):
    """Test that using a binary package name as input resolves correctly"""
    # vim-common is a binary package, but resolve-bin should handle it
    # by finding its source and then listing all binaries from that source
    result = run_predose(sample_packages_file, ['--resolve-bin'], "vim\n")

    assert result.returncode == 0, f"Error: {result.stderr}"
    output_lines = sorted(result.stdout.strip().split('\n'))

    # Should still list all vim binaries
    expected = sorted(["vim-common", "vim-tiny", "vim"])
    assert output_lines == expected, f"Expected {expected}, got {output_lines}"


def test_resolve_bin_empty_input(sample_packages_file):
    """Test with empty input"""
    result = run_predose(sample_packages_file, ['--resolve-bin'], "")

    assert result.returncode == 0, f"Error: {result.stderr}"
    output = result.stdout.strip()

    # Should output nothing
    assert output == "", f"Expected empty output, got '{output}'"


def test_resolve_bin_with_comments(sample_packages_file):
    """Test that comments in input are ignored"""
    input_data = "# This is a comment\nvim\n# Another comment\ncurl\n"

    result = run_predose(sample_packages_file, ['--resolve-bin'], input_data)

    assert result.returncode == 0, f"Error: {result.stderr}"
    output_lines = sorted(result.stdout.strip().split('\n'))

    assert output_lines == sorted(["vim-common", "vim-tiny", "vim", "curl", "libcurl4"])


def test_resolve_bin_whitespace_handling(sample_packages_file):
    """Test handling of whitespace in input"""
    input_data = "  vim  \n  \tcurl\t  \n"

    result = run_predose(sample_packages_file, ['--resolve-bin'], input_data)

    assert result.returncode == 0, f"Error: {result.stderr}"
    output_lines = sorted(result.stdout.strip().split('\n'))

    assert output_lines == sorted(["vim-common", "vim-tiny", "vim", "curl", "libcurl4"])


def test_resolve_bin_source_with_single_binary(sample_packages_file):
    """Test resolving a source that produces only one binary package"""
    result = run_predose(sample_packages_file, ['--resolve-bin'], "nano\n")

    assert result.returncode == 0, f"Error: {result.stderr}"
    output_lines = result.stdout.strip().split('\n')

    assert len(output_lines) == 1, f"Expected 1 line, got {len(output_lines)}"
    assert output_lines[0] == "nano"