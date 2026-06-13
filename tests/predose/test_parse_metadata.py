import pytest
import os
import re
import logging
from pathlib import Path
from predose import Metadata

logging.basicConfig(level=logging.WARNING)

def test_parse_metadata_packages():
    """Test parsing Packages file"""
    data_dir = Path(__file__).parent / "data"
    packages_file = data_dir / "sample_Packages"

    meta = Metadata.from_file(packages_file)

    assert meta.is_bin == True
    assert isinstance(meta.packages, dict)

    expected_package_count = 891
    assert len(meta.packages) == expected_package_count

    for pkg_key, entry in meta.packages.items():
        assert isinstance(pkg_key, tuple)
        assert len(pkg_key) == 2
        assert isinstance(pkg_key[0], str)
        assert isinstance(pkg_key[1], str)
        assert isinstance(entry.version, str)
        assert isinstance(entry.source, str)
        assert isinstance(entry.source_version, str)
        assert isinstance(entry.depends, list)
        assert isinstance(entry.block, str)

def test_parse_metadata_sources():
    data_dir = Path(__file__).parent / "data"
    packages_file = data_dir / "sample_Sources"

    meta = Metadata.from_file(packages_file)

    assert meta.is_bin == False
    assert isinstance(meta.packages, dict)

    expected_package_count = 600
    assert len(meta.packages) == expected_package_count

    for pkg_key, entry in meta.packages.items():
        assert isinstance(pkg_key, tuple)
        assert len(pkg_key) == 2
        assert isinstance(pkg_key[0], str)
        assert isinstance(pkg_key[1], str)
        assert isinstance(entry.version, str)
        assert isinstance(entry.source, str)
        assert isinstance(entry.source_version, str)
        assert isinstance(entry.depends, list)
        assert isinstance(entry.block, str)

def test_parse_metadata_file_not_found():
    """Test handling of non-existent file"""
    with pytest.raises(FileNotFoundError):
        Metadata.from_file("non_existent_file")

def test_parse_metadata_empty_file(tmp_path):
    """Test handling of empty file"""
    empty_file = tmp_path / "empty_file"
    empty_file.write_text("")

    meta = Metadata.from_file(empty_file)
    assert meta.packages == {}
    assert meta.src_dict == {}
    assert meta.bin_dict == {}

def test_parse_metadata_malformed_content(tmp_path):
    """Test handling of malformed content"""
    malformed_file = tmp_path / "malformed_file"
    malformed_content = """Package: test-package
Malformed line without colon
Version: 1.0
"""
    malformed_file.write_text(malformed_content)

    meta = Metadata.from_file(malformed_file)

    assert ("test-package", "1.0") in meta.packages
    assert meta.packages[("test-package", "1.0")].version == "1.0"

def test_package_specific_fields():
    """Test specific fields in parsed package data"""
    data_dir = Path(__file__).parent / "data"
    packages_file = data_dir / "sample_Packages"

    meta = Metadata.from_file(packages_file)

    for pkg_key, entry in list(meta.packages.items())[:1]:
        assert isinstance(entry.version, str)
        assert isinstance(entry.source, str)
        assert isinstance(entry.source_version, str)
        assert isinstance(entry.depends, list)
        assert isinstance(entry.block, str)

def test_provides_mapping():
    """Test that provides mapping works correctly"""
    data_dir = Path(__file__).parent / "data"
    packages_file = data_dir / "sample_Packages"

    meta = Metadata.from_file(packages_file)

    assert isinstance(meta.prov_dict, dict)
    print(len(meta.prov_dict))
    for k,v in meta.prov_dict.items():
        print(k, v)

def test_binary_to_source_mapping():
    """Test binary to source mapping"""
    data_dir = Path(__file__).parent / "data"
    sources_file = data_dir / "sample_Sources"

    meta = Metadata.from_file(sources_file)

    assert isinstance(meta.src_dict, dict)
    assert isinstance(meta.bin_dict, dict)
