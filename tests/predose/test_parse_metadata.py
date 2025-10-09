import pytest
import os
import re
import logging
from pathlib import Path
from predose import parse_metadata

# Set up logging for tests
logging.basicConfig(level=logging.WARNING)

def test_parse_metadata_packages():
    """Test parsing Packages file"""
    data_dir = Path(__file__).parent / "data"
    packages_file = data_dir / "sample_Packages"

    # Parse the metadata - for Packages file, we need to pass empty dicts for src_dict and prov_dict
    pkg_dict = parse_metadata(packages_file, {}, {}, {})

    # Test basic structure
    assert isinstance(pkg_dict, dict)

    # Test that packages were parsed (replace with actual expected count)
    expected_package_count = 888  # Replace with actual expected count
    assert len(pkg_dict) == expected_package_count

    # Test that each package has required fields
    for pkg_name, pkg_data in pkg_dict.items():
        assert isinstance(pkg_name, str)
        assert isinstance(pkg_data, dict)
        assert 'version' in pkg_data
        assert 'source' in pkg_data
        assert 'source_version' in pkg_data
        assert 'depends' in pkg_data
        assert 'block' in pkg_data

def test_parse_metadata_sources():
    """Test parsing Sources file"""
    data_dir = Path(__file__).parent / "data"
    sources_file = data_dir / "sample_Sources"

    # Parse the metadata - for Sources file, we need to pass src_dict
    src_dict = {}
    bin_dict = {}
    parse_metadata(sources_file, src_dict, None, bin_dict)

    # Test basic structure
    assert isinstance(src_dict, dict)
    assert isinstance(bin_dict, dict)

    # Test that sources were parsed (replace with actual expected count)
    expected_source_count = 1213  # Replace with actual expected count
    assert len(src_dict) == expected_source_count

    # Test that each source has binary mappings
    for bin_name, src_name in src_dict.items():
        assert isinstance(bin_name, str)
        assert isinstance(src_name, str)

def test_parse_metadata_file_not_found():
    """Test handling of non-existent file"""
    with pytest.raises(FileNotFoundError):
        parse_metadata("non_existent_file", {}, {}, {})

def test_parse_metadata_empty_file(tmp_path):
    """Test handling of empty file"""
    empty_file = tmp_path / "empty_file"
    empty_file.write_text("")

    # Should return empty dictionary for Packages file
    pkg_dict = parse_metadata(empty_file, {}, {}, {})
    assert pkg_dict == {}

    # Should populate empty dictionaries for Sources file
    src_dict = {}
    bin_dict = {}
    parse_metadata(empty_file, src_dict, None, bin_dict)
    assert src_dict == {}
    assert bin_dict == {}

def test_parse_metadata_malformed_content(tmp_path):
    """Test handling of malformed content"""
    malformed_file = tmp_path / "malformed_file"
    malformed_content = """Package: test-package
Malformed line without colon
Version: 1.0
"""
    malformed_file.write_text(malformed_content)

    # Should handle malformed lines gracefully
    pkg_dict = parse_metadata(malformed_file, {}, {}, {})

    # Should still parse the valid package
    assert "test-package" in pkg_dict
    assert pkg_dict["test-package"]["version"] == "1.0"

def test_package_specific_fields():
    """Test specific fields in parsed package data"""
    data_dir = Path(__file__).parent / "data"
    packages_file = data_dir / "sample_Packages"

    pkg_dict = parse_metadata(packages_file, {}, {}, {})

    # Test a specific package if known to exist
    for pkg_name, pkg_data in list(pkg_dict.items())[:1]:  # Test first package
        assert 'version' in pkg_data
        assert 'source' in pkg_data
        assert 'source_version' in pkg_data
        assert 'depends' in pkg_data
        assert isinstance(pkg_data['depends'], list)
        assert 'block' in pkg_data

def test_provides_mapping():
    """Test that provides mapping works correctly"""
    data_dir = Path(__file__).parent / "data"
    packages_file = data_dir / "sample_Packages"

    prov_dict = {}
    pkg_dict = parse_metadata(packages_file, {}, prov_dict, {})

    # Test that provides mappings were created
    assert isinstance(prov_dict, dict)
    # Add specific tests based on expected provides relationships

def test_binary_to_source_mapping():
    """Test binary to source mapping"""
    data_dir = Path(__file__).parent / "data"
    sources_file = data_dir / "sample_Sources"

    src_dict = {}
    bin_dict = {}
    parse_metadata(sources_file, src_dict, None, bin_dict)

    # Test that mappings were created
    assert isinstance(src_dict, dict)
    assert isinstance(bin_dict, dict)
    # Add specific tests based on expected mappings
