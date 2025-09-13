import pytest
import os
from pathlib import Path
from pre_dose import parse_metadata

def test_parse_metadata_packages():
    """Test parsing Packages file"""
    data_dir = Path(__file__).parent / "data"
    packages_file = data_dir / "sample_Packages"
    
    # Parse the metadata
    pkg_dict, prov_dict, bin_dict = parse_metadata(packages_file)
    
    # Test basic structure
    assert isinstance(pkg_dict, dict)
    assert isinstance(prov_dict, dict)
    assert isinstance(bin_dict, dict)
    
    # Test that packages were parsed (using placeholders)
    assert len(pkg_dict) == pytest.approx(N, abs=0)  # Replace N with actual count
    assert len(prov_dict) == pytest.approx(M, abs=0)  # Replace M with actual count
    assert len(bin_dict) == pytest.approx(K, abs=0)   # Replace K with actual count
    
    # Test that each package has required fields
    for pkg_name, pkg_data in pkg_dict.items():
        assert isinstance(pkg_name, str)
        assert isinstance(pkg_data, dict)
        assert 'Version' in pkg_data
        assert 'Architecture' in pkg_data

def test_parse_metadata_sources():
    """Test parsing Sources file"""
    data_dir = Path(__file__).parent / "data"
    sources_file = data_dir / "sample_Sources"
    
    # Parse the metadata
    src_dict = parse_metadata(sources_file)
    
    # Test basic structure
    assert isinstance(src_dict, dict)
    
    # Test that sources were parsed (using placeholder)
    assert len(src_dict) == pytest.approx(P, abs=0)  # Replace P with actual count
    
    # Test that each source has required fields
    for src_name, src_data in src_dict.items():
        assert isinstance(src_name, str)
        assert isinstance(src_data, dict)
        # Add specific field checks based on Sources file structure

def test_parse_metadata_file_not_found():
    """Test handling of non-existent file"""
    with pytest.raises(FileNotFoundError):
        parse_metadata("non_existent_file")

def test_parse_metadata_empty_file(tmp_path):
    """Test handling of empty file"""
    empty_file = tmp_path / "empty_file"
    empty_file.write_text("")
    
    # Should return empty dictionaries for Packages file
    pkg_dict, prov_dict, bin_dict = parse_metadata(empty_file)
    
    assert pkg_dict == {}
    assert prov_dict == {}
    assert bin_dict == {}
    
    # Should return empty dictionary for Sources file
    # (This might need adjustment based on actual function behavior)

def test_parse_metadata_malformed_content(tmp_path):
    """Test handling of malformed content"""
    malformed_file = tmp_path / "malformed_file"
    malformed_content = """Package: test-package
Malformed line without colon
Version: 1.0
"""
    malformed_file.write_text(malformed_content)
    
    # Should handle malformed lines gracefully
    # The exact behavior depends on the parse_metadata implementation
    result = parse_metadata(malformed_file)
    
    # Basic type check - should return dictionaries
    if isinstance(result, tuple):
        # Packages file - returns 3 dicts
        assert len(result) == 3
        assert all(isinstance(d, dict) for d in result)
    else:
        # Sources file - returns 1 dict
        assert isinstance(result, dict)

# Optional: Add specific field validation tests
def test_package_specific_fields():
    """Test specific fields in parsed package data"""
    data_dir = Path(__file__).parent / "data"
    packages_file = data_dir / "sample_Packages"
    
    pkg_dict, prov_dict, bin_dict = parse_metadata(packages_file)
    
    # Test a specific package if known to exist
    for pkg_name, pkg_data in list(pkg_dict.items())[:1]:  # Test first package
        assert 'Package' in pkg_data
        assert 'Version' in pkg_data
        assert 'Architecture' in pkg_data
        # Add more field checks based on actual data structure