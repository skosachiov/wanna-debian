import pytest
import json
import tempfile
import os
from unittest.mock import Mock, patch, mock_open, MagicMock
import sys
from io import StringIO

# Import the functions from your script
# Note: You may need to adjust imports based on your project structure
from distrotracker import (
    parse_requirement_line,
    check_version,
    write_metadata_index,
    update_metadata_index,
    should_download_file
)


class TestParseRequirementLine:
    """Test cases for parse_requirement_line function"""
    
    def test_parse_basic_requirement(self):
        """Test parsing basic requirement with version constraint"""
        line = "libpython3.13 (>= 3.13.0~rc3)"
        result = parse_requirement_line(line)
        assert result == ("libpython3.13", ">=", "3.13.0~rc3")
    
    def test_parse_equals_operator(self):
        """Test parsing with equals operator"""
        line = "package-name (= 1.2.3)"
        result = parse_requirement_line(line)
        assert result == ("package-name", "=", "1.2.3")
    
    def test_parse_greater_less_operators(self):
        """Test parsing with >> and << operators"""
        line = "test-pkg (>> 2.0.0)"
        result = parse_requirement_line(line)
        assert result == ("test-pkg", ">>", "2.0.0")
        
        line = "test-pkg (<< 1.5.0)"
        result = parse_requirement_line(line)
        assert result == ("test-pkg", "<<", "1.5.0")
    
    def test_parse_with_spaces(self):
        """Test parsing with various spacing"""
        line = "package  (  >=  1.0.0  )"
        result = parse_requirement_line(line)
        assert result == ("package", ">=", "1.0.0")
    
    def test_parse_no_version(self):
        """Test parsing line without version constraint"""
        line = "package-name"
        result = parse_requirement_line(line)
        assert result == ("package-name", ">=", "0")
    
    def test_parse_empty_line(self):
        """Test parsing empty line"""
        line = ""
        result = parse_requirement_line(line)
        assert result is None
    
    def test_parse_line_with_comment(self):
        """Test parsing line with trailing comment"""
        line = "package (>= 1.0.0) # This is a comment"
        result = parse_requirement_line(line)
        assert result == ("package", ">=", "1.0.0")
    

class TestCheckVersion:
    """Test cases for check_version function"""
    
    def test_version_equal(self):
        """Test equals operator"""
        assert check_version("1.0.0", "=", "1.0.0") is True
        assert check_version("1.0.0", "=", "1.0.1") is False
    
    def test_version_greater_equal(self):
        """Test greater than or equal operator"""
        assert check_version("1.0.0", ">=", "1.0.0") is True
        assert check_version("1.0.1", ">=", "1.0.0") is True
        assert check_version("0.9.0", ">=", "1.0.0") is False
    
    def test_version_less_equal(self):
        """Test less than or equal operator"""
        assert check_version("1.0.0", "<=", "1.0.0") is True
        assert check_version("0.9.0", "<=", "1.0.0") is True
        assert check_version("1.0.1", "<=", "1.0.0") is False
    
    def test_version_greater(self):
        """Test strictly greater operator"""
        assert check_version("1.0.1", ">>", "1.0.0") is True
        assert check_version("1.0.0", ">>", "1.0.0") is False
        assert check_version("0.9.0", ">>", "1.0.0") is False
    
    def test_version_less(self):
        """Test strictly less operator"""
        assert check_version("0.9.0", "<<", "1.0.0") is True
        assert check_version("1.0.0", "<<", "1.0.0") is False
        assert check_version("1.0.1", "<<", "1.0.0") is False
    
    def test_complex_versions(self):
        """Test complex version strings"""
        assert check_version("1.0.0~rc1", ">=", "1.0.0") is False
        assert check_version("2:1.0.0", ">=", "1.0.0") is True


class TestWriteMetadataIndex:
    """Test cases for write_metadata_index function"""
    
    def test_write_metadata_index_success(self):
        """Test successful writing of metadata index"""
        test_data = [
            {"package": "test1", "version": "1.0.0", "arch": "amd64"},
            {"package": "test2", "version": "2.0.0", "arch": "arm64"}
        ]
        
        with patch('builtins.open', mock_open()) as mock_file:
            write_metadata_index("test.json", test_data)
            
            # Verify file was opened for writing
            mock_file.assert_called_once_with("test.json", 'w', encoding='utf-8')
            
            # Get the written content
            handle = mock_file()
            write_calls = handle.write.call_args_list
            
            # Join all write calls to get the full content
            written_content = ''.join(call[0][0] for call in write_calls)
            
            # Verify JSON structure
            assert written_content.startswith('[\n')
            assert written_content.endswith('\n]')
            assert '"package":"test1"' in written_content
            assert '"version":"1.0.0"' in written_content
    
    def test_write_metadata_index_io_error(self):
        """Test handling of IO error during write"""
        test_data = [{"package": "test1", "version": "1.0.0"}]
        
        with patch('builtins.open', side_effect=IOError("Permission denied")):
            with patch('logging.error') as mock_logging:
                write_metadata_index("test.json", test_data)
                mock_logging.assert_called_once()


class TestUpdateMetadataIndex:
    """Test cases for update_metadata_index function"""
    
    def test_update_metadata_index_basic(self):
        """Test basic metadata index update"""
        mock_file_content = """Package: test-package
Version: 1.0.0
Architecture: amd64
Depends: libc6 (>= 2.14), libssl1.1

Package: another-package
Version: 2.0.0
Architecture: arm64
Source: another-source
Source-Version: 2.0.0
Depends: libc6

"""
        packages = []
        
        with patch('builtins.open', mock_open(read_data=mock_file_content)):
            with patch('logging.debug') as mock_logging:
                result = update_metadata_index(
                    "test_file", packages, "buster", "main", "amd64"
                )
                
                assert len(result) == 2
                assert result[0]['package'] == 'test-package'
                assert result[0]['version'] == '1.0.0'
                assert result[0]['dist'] == 'buster'
                assert result[0]['comp'] == 'main'
                assert result[0]['arch'] == 'amd64'
                assert result[0]['source'] == 'test-package'
                assert result[0]['source_version'] == '1.0.0'
                
                assert result[1]['package'] == 'another-package'
                assert result[1]['source'] == 'another-source'
                assert result[1]['source_version'] == '2.0.0'
                
                mock_logging.assert_called_once()
    
    def test_update_metadata_index_with_source(self):
        """Test metadata update with source package information"""
        mock_file_content = """Package: binary-package
Version: 1.5.0
Source: source-package (1.5.0-1)
Architecture: amd64
Depends: dep1, dep2

"""
        packages = []
        
        with patch('builtins.open', mock_open(read_data=mock_file_content)):
            result = update_metadata_index(
                "test_file", packages, "bullseye", "main", "amd64"
            )
            
            assert len(result) == 1
            assert result[0]['package'] == 'binary-package'
            assert result[0]['source'] == 'source-package'
            assert result[0]['source_version'] == '1.5.0-1'
    

class TestShouldDownloadFile:
    """Test cases for should_download_file function"""
    
    def test_should_download_when_file_missing(self):
        """Test that download is needed when file doesn't exist"""
        with patch('os.path.exists', return_value=False):
            result = should_download_file("/nonexistent/file", "Thu, 01 Jan 1970 00:00:00 GMT")
            assert result is True
    
    def test_should_download_when_remote_newer(self):
        """Test that download is needed when remote file is newer"""
        with patch('os.path.exists', return_value=True):
            with patch('os.path.getmtime', return_value=1000000000):  # Old file
                result = should_download_file(
                    "/existing/file", 
                    "Thu, 01 Jan 2020 00:00:00 GMT"  # Newer date
                )
                assert result is True
    
    def test_should_not_download_when_local_newer(self):
        """Test that download is not needed when local file is newer"""
        with patch('os.path.exists', return_value=True):
            with patch('os.path.getmtime', return_value=2000000000):  # New file
                result = should_download_file(
                    "/existing/file", 
                    "Thu, 01 Jan 2020 00:00:00 GMT"  # Older date
                )
                assert result is False


class TestIntegration:
    """Integration tests with mocked dependencies"""
    
    @patch('sys.stdin', StringIO('libtest (>= 1.0.0)\npackage2\n'))
    @patch('builtins.open')
    @patch('os.path.exists')
    def test_find_versions_integration(self, mock_exists, mock_open_file):
        """Test the find_versions function with mocked input"""
        # Mock file existence
        mock_exists.return_value = True
        
        # Mock JSON file content
        test_data = [
            {
                "package": "libtest", 
                "version": "1.5.0", 
                "dist": "buster", 
                "arch": "amd64",
                "source": "libtest",
                "source_version": "1.5.0",
                "depends": "abc12345"
            },
            {
                "package": "libtest", 
                "version": "0.9.0", 
                "dist": "buster", 
                "arch": "amd64",
                "source": "libtest", 
                "source_version": "0.9.0",
                "depends": "def67890"
            }
        ]
        
        mock_open_file.return_value = MagicMock()
        mock_open_file.return_value.__enter__.return_value.read.return_value = json.dumps(test_data)
        
        # Import the function
        from distrotracker import find_versions
        
        # Capture stdout
        with patch('sys.stdout') as mock_stdout:
            find_versions(
                sys.stdin, 
                "/tmp/test_index.json", 
                None, None, False, False, "package"
            )
            
            # Verify output was written to stdout
            assert mock_stdout.write.called


# Test fixtures for common test data
@pytest.fixture
def sample_package_data():
    """Fixture providing sample package data for tests"""
    return [
        {
            "package": "test-package",
            "version": "1.0.0",
            "dist": "buster",
            "comp": "main", 
            "arch": "amd64",
            "source": "test-package",
            "source_version": "1.0.0",
            "depends": "abc12345"
        }
    ]


@pytest.fixture
def mock_file_operations():
    """Fixture to mock file operations"""
    with patch('builtins.open'), \
         patch('os.path.exists'), \
         patch('os.makedirs'):
        yield


if __name__ == "__main__":
    pytest.main([__file__, "-v"])