from module.update.download import (
    build_checksum_mismatch_detail,
    build_download_error_message,
)
from module.update.model import format_size, normalize_sha256


class TestFormatSize:
    def test_bytes(self):
        assert format_size(100) == "100 B"

    def test_kilobytes(self):
        assert format_size(1024) == "1.0 KB"

    def test_megabytes(self):
        assert format_size(1024 * 1024) == "1.0 MB"

    def test_gigabytes(self):
        assert format_size(1024 * 1024 * 1024) == "1.0 GB"

    def test_none(self):
        assert format_size(None) == "--"

    def test_zero(self):
        assert format_size(0) == "0 B"

    def test_large_number(self):
        result = format_size(5 * 1024 * 1024 * 1024)
        assert "GB" in result


class TestNormalizeSha256:
    def test_valid(self):
        sha = "a" * 64
        assert normalize_sha256(sha) == sha

    def test_with_prefix(self):
        sha = f"sha256:{'a' * 64}"
        assert normalize_sha256(sha) == "a" * 64

    def test_empty(self):
        assert normalize_sha256("") == ""

    def test_none(self):
        assert normalize_sha256(None) == ""


class TestBuildDownloadErrorMessage:
    def test_generic_error(self):
        error = Exception("test error")
        result = build_download_error_message(error)
        assert "test error" in result

    def test_checksum_mismatch(self):
        from module.update.model import ChecksumMismatchError
        error = ChecksumMismatchError("checksum failed")
        result = build_download_error_message(error)
        assert "checksum failed" in result


class TestBuildChecksumMismatchDetail:
    def test_detail_message(self):
        result = build_checksum_mismatch_detail("abc123", "def456")
        assert "abc123" in result
        assert "def456" in result
