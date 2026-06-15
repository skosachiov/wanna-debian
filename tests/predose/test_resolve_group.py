import pytest
import tempfile
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from predose import Metadata


@pytest.fixture
def sample_sources_metadata():
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
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(sample_sources_metadata)
        return f.name


@pytest.fixture
def sample_binary_file(sample_binary_metadata):
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(sample_binary_metadata)
        return f.name


@pytest.fixture
def setup_origin_metadata(sample_sources_file):
    meta = Metadata.from_file(sample_sources_file)
    os.unlink(sample_sources_file)
    return meta


@pytest.fixture
def setup_target_metadata(sample_binary_file):
    meta = Metadata.from_file(sample_binary_file)
    os.unlink(sample_binary_file)
    return meta


def make_pkg_key(name, version=""):
    return (name, version) if version else (name, "")


def test_resolve_group_on_source_metadata(setup_origin_metadata):
    meta = setup_origin_metadata
    result = meta.resolve_group(make_pkg_key("linux-headers"))
    names = result.split('\n')
    assert len(names) == 3
    assert 'linux-image' in names
    assert 'linux-headers' in names
    assert 'linux-libc-dev' in names

    result = meta.resolve_group(make_pkg_key("libc-bin"))
    names = result.split('\n')
    assert len(names) == 3
    assert 'libc6' in names
    assert 'libc6-dev' in names
    assert 'libc-bin' in names


def test_resolve_group_on_binary_metadata(setup_target_metadata):
    meta = setup_target_metadata
    result = meta.resolve_group(make_pkg_key("linux-image"))
    names = result.split('\n')
    assert len(names) == 3
    assert 'linux-image' in names
    assert 'linux-headers' in names
    assert 'linux-libc-dev' in names

    result = meta.resolve_group(make_pkg_key("libc6"))
    names = result.split('\n')
    assert len(names) == 3
    assert 'libc6' in names
    assert 'libc6-dev' in names
    assert 'libc-bin' in names


def test_resolve_group_multiple_binaries_same_source():
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
    os.unlink(temp_file)

    result = meta.resolve_group(make_pkg_key("linux-image"))
    names = result.split('\n')
    assert 'linux-image' in names
    assert 'linux-headers' in names
    assert 'linux-firmware' in names


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
