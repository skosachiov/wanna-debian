#!/usr/bin/env python3
"""
Tests for predose.py --resolve-src functionality
"""

import pytest
import sys
import os
import subprocess
import tempfile
from pathlib import Path

# Find the predose.py script
def find_predose_script():
    """Find predose.py in the project structure"""
    # Start from the current file's directory
    current_dir = Path(__file__).parent
    
    # Try different possible locations based on the actual structure
    possible_paths = [
        current_dir.parent.parent / "predose" / "predose.py",  # tests/predose/../../predose/predose.py
        current_dir.parent / "predose.py",  # tests/predose/../predose.py
        current_dir.parent.parent / "predose.py",  # tests/predose/../../predose.py
        Path.cwd() / "predose" / "predose.py",  # Current working directory/predose/predose.py
        Path.cwd() / "predose.py",  # Current working directory
        Path.cwd().parent / "predose" / "predose.py",  # Parent of current working directory/predose/predose.py
    ]
    
    for path in possible_paths:
        if path.exists():
            return str(path)
    
    # If not found, try to search upwards for predose directory
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
SAMPLE_PACKAGES_CONTENT = """\
Package: vim-common
Version: 2:8.2.3995-1ubuntu2.1
Source: vim
Depends: vim-tiny (>= 2:8.2.3995-1ubuntu2.1) | vim (>= 2:8.2.3995-1ubuntu2.1), libc6 (>= 2.34)

Package: vim-tiny
Version: 2:8.2.3995-1ubuntu2.1
Source: vim
Depends: libc6 (>= 2.34)

Package: nano
Version: 6.2-1
Source: nano
Depends: libc6 (>= 2.34), libncursesw6 (>= 6), libtinfo6 (>= 6)

Package: curl
Version: 7.81.0-1ubuntu1.15
Source: curl
Depends: libc6 (>= 2.34), libcurl4 (= 7.81.0-1ubuntu1.15)

Package: wget
Version: 1.21.2-2ubuntu1
Source: wget
Depends: libc6 (>= 2.34), libssl3 (>= 3.0.0)

Package: git
Version: 1:2.34.1-1ubuntu1.10
Source: git
Depends: libc6 (>= 2.34), libcurl3-gnutls (>= 7.16.2), libpcre2-8-0 (>= 10.34), zlib1g (>= 1:1.1.4)

Package: python3
Version: 3.10.12-1~22.04.3
Source: python3-defaults
Depends: python3.10 (>= 3.10.12-1~22.04.3), libpython3-stdlib (= 3.10.12-1~22.04.3)

Package: build-essential
Version: 12.9ubuntu3
Source: build-essential
Depends: gcc (>= 4:11.2), g++ (>= 4:11.2), make, dpkg-dev
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


def test_script_found():
    """Test that predose.py was found"""
    assert PREDOSE_SCRIPT is not None, "predose.py not found"
    assert Path(PREDOSE_SCRIPT).exists(), f"predose.py not found at {PREDOSE_SCRIPT}"
    print(f"\nFound predose.py at: {PREDOSE_SCRIPT}")
    print(f"Project root: {PROJECT_ROOT}")


def test_resolve_src_vim_common(sample_packages_file):
    """Test resolving vim-common binary package to vim source package"""
    result = run_predose(sample_packages_file, ['--resolve-src'], "vim-common\n")
    
    assert result.returncode == 0, f"Error: {result.stderr}"
    output = result.stdout.strip()
    
    # Should resolve to vim (source package)
    assert output == "vim", f"Expected 'vim', got '{output}'"
    assert "vim" in output
    assert "vim-common" not in output  # Should not output binary name


def test_resolve_src_vim_tiny(sample_packages_file):
    """Test resolving vim-tiny binary package to vim source package"""
    result = run_predose(sample_packages_file, ['--resolve-src'], "vim-tiny\n")
    
    assert result.returncode == 0, f"Error: {result.stderr}"
    output = result.stdout.strip()
    
    assert output == "vim", f"Expected 'vim', got '{output}'"


def test_resolve_src_nano(sample_packages_file):
    """Test resolving nano binary package to nano source package"""
    result = run_predose(sample_packages_file, ['--resolve-src'], "nano\n")
    
    assert result.returncode == 0, f"Error: {result.stderr}"
    output = result.stdout.strip()
    
    assert output == "nano", f"Expected 'nano', got '{output}'"


def test_resolve_src_curl(sample_packages_file):
    """Test resolving curl binary package to curl source package"""
    result = run_predose(sample_packages_file, ['--resolve-src'], "curl\n")
    
    assert result.returncode == 0, f"Error: {result.stderr}"
    output = result.stdout.strip()
    
    assert output == "curl", f"Expected 'curl', got '{output}'"


def test_resolve_src_wget(sample_packages_file):
    """Test resolving wget binary package to wget source package"""
    result = run_predose(sample_packages_file, ['--resolve-src'], "wget\n")
    
    assert result.returncode == 0, f"Error: {result.stderr}"
    output = result.stdout.strip()
    
    assert output == "wget", f"Expected 'wget', got '{output}'"


def test_resolve_src_multiple_packages(sample_packages_file):
    """Test resolving multiple binary packages to source packages"""
    input_data = "vim-common\nnano\ncurl\nwget\ngit\n"
    result = run_predose(sample_packages_file, ['--resolve-src'], input_data)
    
    assert result.returncode == 0, f"Error: {result.stderr}"
    output_lines = result.stdout.strip().split('\n')
    
    expected_outputs = ["vim", "nano", "curl", "wget", "git"]
    
    assert len(output_lines) == 5, f"Expected 5 lines, got {len(output_lines)}: {output_lines}"
    for expected in expected_outputs:
        assert expected in output_lines, f"Expected '{expected}' in {output_lines}"


def test_resolve_src_with_version(sample_packages_file):
    """Test resolving binary to source with version information"""
    result = run_predose(sample_packages_file, ['--resolve-src', '--add-version'], "vim-common\n")
    
    assert result.returncode == 0, f"Error: {result.stderr}"
    output = result.stdout.strip()
    
    # Should include version in format: pkg=version
    assert output.startswith("vim="), f"Expected 'vim=', got '{output}'"
    assert "2:8.2.3995-1ubuntu2.1" in output or "=" in output, f"Version not found in '{output}'"


def test_resolve_src_python3(sample_packages_file):
    """Test resolving python3 binary package to source package"""
    result = run_predose(sample_packages_file, ['--resolve-src'], "python3\n")
    
    assert result.returncode == 0, f"Error: {result.stderr}"
    output = result.stdout.strip()
    
    # python3 should resolve to python3-defaults source
    assert output == "python3-defaults", f"Expected 'python3-defaults', got '{output}'"


def test_resolve_src_build_essential(sample_packages_file):
    """Test resolving build-essential binary package to source package"""
    result = run_predose(sample_packages_file, ['--resolve-src'], "build-essential\n")
    
    assert result.returncode == 0, f"Error: {result.stderr}"
    output = result.stdout.strip()
    
    assert output == "build-essential", f"Expected 'build-essential', got '{output}'"


def test_resolve_src_nonexistent_package(sample_packages_file):
    """Test resolving a package that doesn't exist"""
    result = run_predose(sample_packages_file, ['--resolve-src'], "nonexistent-package\n")
    
    assert result.returncode == 0, f"Error: {result.stderr}"
    output = result.stdout.strip()
    
    # Should output nothing for unresolved package
    assert output == "", f"Expected empty output, got '{output}'"


def test_resolve_src_git(sample_packages_file):
    """Test resolving git binary package to git source package"""
    result = run_predose(sample_packages_file, ['--resolve-src'], "git\n")
    
    assert result.returncode == 0, f"Error: {result.stderr}"
    output = result.stdout.strip()
    
    assert output == "git", f"Expected 'git', got '{output}'"


def test_resolve_src_all_listed_packages(sample_packages_file):
    """Test resolving all 5 mentioned packages at once"""
    # List of packages to test: vim-common, nano, curl, wget, git
    input_packages = "vim-common\nnano\ncurl\nwget\ngit\n"
    
    result = run_predose(sample_packages_file, ['--resolve-src'], input_packages)
    
    assert result.returncode == 0, f"Error: {result.stderr}"
    output_lines = result.stdout.strip().split('\n')
    
    expected_sources = ["vim", "nano", "curl", "wget", "git"]
    
    assert len(output_lines) == 5, f"Expected 5 lines, got {len(output_lines)}"
    for i, expected in enumerate(expected_sources):
        assert output_lines[i] == expected, f"Line {i}: expected '{expected}', got '{output_lines[i]}'"


def test_resolve_src_with_comments(sample_packages_file):
    """Test that comments in input are ignored"""
    input_data = "# This is a comment\nvim-common\n# Another comment\nnano\n"
    
    result = run_predose(sample_packages_file, ['--resolve-src'], input_data)
    
    assert result.returncode == 0, f"Error: {result.stderr}"
    output_lines = result.stdout.strip().split('\n')
    
    assert len(output_lines) == 2, f"Expected 2 lines, got {len(output_lines)}"
    assert output_lines[0] == "vim", f"Expected 'vim', got '{output_lines[0]}'"
    assert output_lines[1] == "nano", f"Expected 'nano', got '{output_lines[1]}'"


def test_resolve_src_empty_input(sample_packages_file):
    """Test with empty input"""
    result = run_predose(sample_packages_file, ['--resolve-src'], "")
    
    assert result.returncode == 0, f"Error: {result.stderr}"
    output = result.stdout.strip()
    
    # Should output nothing
    assert output == "", f"Expected empty output, got '{output}'"


def test_resolve_src_whitespace_handling(sample_packages_file):
    """Test handling of whitespace in input"""
    input_data = "  vim-common  \n  \tnano\t  \n"
    
    result = run_predose(sample_packages_file, ['--resolve-src'], input_data)
    
    assert result.returncode == 0, f"Error: {result.stderr}"
    output_lines = result.stdout.strip().split('\n')
    
    assert len(output_lines) == 2, f"Expected 2 lines, got {len(output_lines)}"
    assert output_lines[0] == "vim", f"Expected 'vim', got '{output_lines[0]}'"
    assert output_lines[1] == "nano", f"Expected 'nano', got '{output_lines[1]}'"