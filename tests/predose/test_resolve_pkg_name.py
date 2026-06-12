import pytest
import logging
from predose import Metadata

logging.basicConfig(level=logging.INFO)

def make_meta(packages, src_dict=None, prov_dict=None):
    meta = Metadata()
    meta.latest_index = {}
    for k in packages:
        pkg_key = (k, "1.0") if isinstance(k, str) else k
        # Use the same key as PkgKey for the latest index
        meta.latest_index[pkg_key[0]] = pkg_key
    meta.packages = {meta.latest_index[k]: None for k in packages}
    if src_dict:
        meta.src_dict = src_dict
    if prov_dict:
        meta.prov_dict = prov_dict
    return meta

def test_resolve_pkg_name_unchanged():
    """Test when package name is already in origin"""
    meta = make_meta({"pkg1", "pkg2", "pkg3"},
                     {"binary1": "source1", "binary2": "source2"},
                     {"provided1": "provider1", "provided2": "provider2"})

    result = meta.resolve_pkg_name("pkg2")
    assert result == ("pkg2", "1.0")

def test_resolve_pkg_name_binary_to_source():
    """Test resolving binary package to source package"""
    meta = make_meta({"source1", "source2"},
                     {"binary1": "source1", "binary2": "source2"},
                     {"provided1": "provider1"})

    result = meta.resolve_pkg_name("binary1")
    assert result == ("source1", "1.0")

def test_resolve_pkg_name_provided_to_source():
    """Test resolving provided package to source package"""
    meta = make_meta({"source1"},
                     {"binary1": "source1", "provider1": "source1"},
                     {"provided1": "provider1"})

    result = meta.resolve_pkg_name("provided1")
    assert result == ("source1", "1.0")

def test_resolve_pkg_name_provided_direct():
    """Test resolving provided package directly to provider"""
    meta = make_meta({"provider1", "source2"},
                     {"binary1": "source1"},
                     {"provided1": "provider1"})

    result = meta.resolve_pkg_name("provided1")
    assert result == ("provider1", "1.0")

def test_resolve_pkg_name_provided_not_found():
    """Test when provided package cannot be resolved"""
    meta = make_meta({"source1"},
                     {"binary1": "source1"},
                     {"provided1": "unknown_provider"})

    result = meta.resolve_pkg_name("provided1")
    assert result is None

def test_resolve_pkg_name_not_found():
    """Test when package name is not found anywhere"""
    meta = make_meta({"pkg1"},
                     {"binary1": "source1"},
                     {"provided1": "provider1"})

    result = meta.resolve_pkg_name("nonexistent")
    assert result is None

def test_resolve_pkg_name_empty_dicts():
    """Test with empty dictionaries"""
    meta = make_meta({"pkg1"})

    result = meta.resolve_pkg_name("pkg1")
    assert result == ("pkg1", "1.0")

    result = meta.resolve_pkg_name("unknown")
    assert result is None

def test_resolve_pkg_name_complex_chain():
    """Test complex resolution chain"""
    meta = make_meta({"ultimate-source"},
                     {"binary1": "ultimate-source",
                      "provider-binary": "ultimate-source"},
                     {"provided-service": "provider-binary",
                      "another-provided": "binary1"})

    result = meta.resolve_pkg_name("provided-service")
    assert result == ("ultimate-source", "1.0")

    result = meta.resolve_pkg_name("another-provided")
    assert result == ("ultimate-source", "1.0")

def test_resolve_pkg_name_case_sensitivity():
    """Test case sensitivity in resolution"""
    meta = make_meta({"Pkg1", "Source1"},
                     {"Binary1": "Source1", "BINARY2": "Source1"},
                     {"Provided1": "Provider1", "PROVIDED2": "PROVIDER2"})

    result = meta.resolve_pkg_name("Pkg1")
    assert result == ("Pkg1", "1.0")

    result = meta.resolve_pkg_name("Binary1")
    assert result == ("Source1", "1.0")

def test_resolve_pkg_name_multiple_options():
    """Test resolution when multiple paths exist"""
    meta = make_meta({"source1", "source2", "direct-provider"},
                     {"binary1": "source1",
                      "binary2": "source2",
                      "binary3": "source1"},
                     {"provided1": "binary1",
                      "provided2": "direct-provider"})

    result = meta.resolve_pkg_name("provided2")
    assert result == ("direct-provider", "1.0")

@pytest.mark.parametrize("pkg_name,expected", [
    ("pkg_in_origin", ("pkg_in_origin", "1.0")),
    ("binary_pkg", ("source_pkg", "1.0")),
    ("provided_pkg", ("source_pkg", "1.0")),
    ("unknown_pkg", None),
    ("direct_provider", ("direct_provider", "1.0")),
])
def test_resolve_pkg_name_parametrized(pkg_name, expected):
    """Parametrized test for various scenarios"""
    meta = make_meta({"pkg_in_origin", "source_pkg", "direct_provider"},
                     {"binary_pkg": "source_pkg", "provider_binary": "source_pkg"},
                     {"provided_pkg": "provider_binary", "other_provided": "unknown"})

    result = meta.resolve_pkg_name(pkg_name)
    assert result == expected
