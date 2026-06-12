import pytest
import tempfile
import os
import sys
from io import StringIO

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from predose import Metadata

@pytest.fixture
def sample_sources_metadata():
    """Sample Sources metadata (source packages)"""
    return """Package: linux
Version: 5.10.0-1
Binary: linux-image, linux-headers, linux-libc-dev
Build-Depends: debhelper, gcc, make

Package: glibc
Version: 2.31-1
Binary: libc6, libc6-dev, libc-bin
Build-Depends: gcc, make

Package: openssl
Version: 1.1.1k-1
Binary: openssl, libssl1.1, libssl-dev
Build-Depends: gcc, make, perl
"""

@pytest.fixture
def sample_binary_metadata():
    """Sample Packages metadata (binary packages)"""
    return """Package: linux-image
Version: 5.10.0-1
Source: linux (5.10.0-1)
Depends: kmod, initramfs-tools

Package: linux-headers
Version: 5.10.0-1
Source: linux (5.10.0-1)
Depends: gcc, make

Package: linux-libc-dev
Version: 5.10.0-1
Source: linux (5.10.0-1)

Package: libc6
Version: 2.31-1
Source: glibc (2.31-1)
Depends: gcc

Package: libc6-dev
Version: 2.31-1
Source: glibc (2.31-1)

Package: libc-bin
Version: 2.31-1
Source: glibc (2.31-1)

Package: libssl1.1
Version: 1.1.1k-1
Source: openssl (1.1.1k-1)
"""

@pytest.fixture
def sample_sources_file(sample_sources_metadata):
    """Create temporary file with source metadata"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(sample_sources_metadata)
        return f.name

@pytest.fixture
def sample_binary_file(sample_binary_metadata):
    """Create temporary file with binary metadata"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(sample_binary_metadata)
        return f.name

@pytest.fixture
def setup_origin_metadata(sample_sources_file):
    """Parse origin metadata (Sources)"""
    meta = Metadata.from_file(sample_sources_file)
    os.unlink(sample_sources_file)
    return meta

@pytest.fixture
def setup_target_metadata(sample_binary_file):
    """Parse target metadata (binary Packages)"""
    meta = Metadata.from_file(sample_binary_file)
    os.unlink(sample_binary_file)
    return meta

def make_pkg_key(name, version=""):
    return (name, version) if version else (name, "")

def test_resolve_group_on_source_metadata(setup_origin_metadata):
    """Test resolve-group on source metadata (is_bin_metadata=False)"""
    meta = setup_origin_metadata

    result = Metadata.handle_resolve_group(
        make_pkg_key("linux"), meta.packages, meta.is_bin, meta.bin_dict, meta.packages
    )
    output_lines = result.split('\n')

    assert len(output_lines) == 3
    assert 'linux-image' in output_lines
    assert 'linux-headers' in output_lines
    assert 'linux-libc-dev' in output_lines

    result = Metadata.handle_resolve_group(
        make_pkg_key("glibc"), meta.packages, meta.is_bin, meta.bin_dict, meta.packages
    )
    output_lines = result.split('\n')

    assert len(output_lines) == 3
    assert 'libc6' in output_lines
    assert 'libc6-dev' in output_lines
    assert 'libc-bin' in output_lines

def test_resolve_group_on_binary_metadata(setup_target_metadata):
    """Test resolve-group on binary metadata (is_bin_metadata=True)"""
    meta = setup_target_metadata

    result = Metadata.handle_resolve_group(
        make_pkg_key("linux-image"), meta.packages, meta.is_bin, meta.bin_dict, meta.packages
    )
    output_lines = result.split('\n')

    assert len(output_lines) == 3
    assert 'linux-image' in output_lines
    assert 'linux-headers' in output_lines
    assert 'linux-libc-dev' in output_lines

    result = Metadata.handle_resolve_group(
        make_pkg_key("libc6"), meta.packages, meta.is_bin, meta.bin_dict, meta.packages
    )
    output_lines = result.split('\n')

    assert len(output_lines) == 3
    assert 'libc6' in output_lines
    assert 'libc6-dev' in output_lines
    assert 'libc-bin' in output_lines

def test_resolve_group_multiple_binaries_same_source():
    """Test that all binaries from same source package are returned"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("""Package: linux-image
Version: 5.10.0-1
Source: linux

Package: linux-headers
Version: 5.10.0-1
Source: linux

Package: linux-firmware
Version: 5.10.0-1
Source: linux
""")
        temp_file = f.name

    meta = Metadata.from_file(temp_file)
    meta.bin_dict[('linux', '')] = ['linux-image', 'linux-headers', 'linux-tools', 'linux-firmware']

    os.unlink(temp_file)

    result = Metadata.handle_resolve_group(
        make_pkg_key("linux-image"), meta.packages, meta.is_bin, meta.bin_dict, meta.packages
    )
    output_lines = result.split('\n')

    assert len(set(output_lines)) == 4
    assert 'linux-image' in output_lines
    assert 'linux-headers' in output_lines
    assert 'linux-tools' in output_lines
    assert 'linux-firmware' in output_lines


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
