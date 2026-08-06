import pytest

from module.update.detect import find_asset
from module.update.model import is_update_available, normalize_sha256


class TestIsUpdateAvailable:
    def test_newer_version_available(self):
        assert is_update_available("1.1.0", "1.0.0") is True

    def test_same_version(self):
        assert is_update_available("1.0.0", "1.0.0") is False

    def test_older_version(self):
        assert is_update_available("0.9.0", "1.0.0") is False

    def test_with_v_prefix(self):
        assert is_update_available("v1.1.0", "v1.0.0") is True

    def test_empty_local(self):
        assert is_update_available("1.0.0", "") is True

    def test_invalid_version_returns_true(self):
        assert is_update_available("invalid", "also_invalid") is True


class TestNormalizeSha256:
    def test_valid_sha256(self):
        sha = "a" * 64
        assert normalize_sha256(sha) == sha

    def test_uppercase(self):
        sha = "A" * 64
        assert normalize_sha256(sha) == "a" * 64

    def test_with_prefix(self):
        sha = f"sha256:{'a' * 64}"
        assert normalize_sha256(sha) == "a" * 64

    def test_empty_string(self):
        assert normalize_sha256("") == ""

    def test_none(self):
        assert normalize_sha256(None) == ""

    def test_invalid_algorithm(self):
        assert normalize_sha256(f"md5:{'a' * 64}") == ""

    def test_too_short(self):
        assert normalize_sha256("abc123") == ""

    def test_too_long(self):
        assert normalize_sha256("a" * 65) == ""


class TestFindAsset:
    def _asset(self, name):
        from module.update.model import UpdateAsset
        return UpdateAsset(name=name, url=f"https://example.com/{name}")

    def test_matches_by_substring(self):
        from module.update.model import UpdateInfo
        info = UpdateInfo(version="v2", assets=[
            self._asset("full.7z"),
            self._asset("patch_from_v1_to_v2"),
        ])
        result = find_asset(info, "patch_from_v1_to_v2")
        assert result is not None
        assert result.name == "patch_from_v1_to_v2"

    def test_empty_assets(self):
        from module.update.model import UpdateInfo
        assert find_asset(UpdateInfo(version="v2"), "patch") is None

    def test_no_match(self):
        from module.update.model import UpdateInfo
        info = UpdateInfo(version="v2", assets=[self._asset("full.7z")])
        assert find_asset(info, "patch_from_v1_to_v2") is None


class TestCheckGithub:
    """GitHub API 检测：镜像回退 / 失败收集 / 资产解析。"""

    def _release(self, version="v2.0.0"):
        return {
            "tag_name": version,
            "body": "release body",
            "html_url": "https://github.com/sparklelcm333/March7thAssistant-personal/releases/tag/v2.0.0",
            "assets": [
                {"name": "patch_from_v1_to_v2", "browser_download_url": "https://x/patch"},
                {"name": "full.7z", "browser_download_url": "https://x/full"},
            ],
        }

    def test_first_mirror_succeeds(self, monkeypatch):
        from module.update import detect
        import requests as req

        def _fake_get(url, timeout=10, headers=None, proxies=None):
            calls.append(url)
            return _FakeResp(200, self._release())

        calls = []
        monkeypatch.setattr("module.update.github_api.requests.get", _fake_get)
        info = detect._check_github(False, "v1.0.0", None)
        assert info is not None
        assert info.version == "v2.0.0"
        assert info.assets[0].name == "patch_from_v1_to_v2"
        assert len(calls) == 1  # 首个成功即停，不重复请求

    def test_falls_back_to_second_mirror(self, monkeypatch):
        from module.update import detect

        def _fake_get(url, timeout=10, headers=None, proxies=None):
            calls.append(url)
            if len(calls) == 1:
                return _FakeResp(500, {})
            return _FakeResp(200, self._release())

        calls = []
        monkeypatch.setattr("module.update.github_api.requests.get", _fake_get)
        info = detect._check_github(False, "v1.0.0", None)
        assert info is not None
        assert len(calls) == 2

    def test_all_mirrors_fail_raises(self, monkeypatch):
        from module.update import detect

        def _fake_get(url, timeout=10, headers=None, proxies=None):
            calls.append(url)
            raise req.ConnectionError("net down")

        import requests as req
        calls = []
        monkeypatch.setattr("module.update.github_api.requests.get", _fake_get)
        with pytest.raises(detect.VersionCheckError, match="net down"):
            detect._check_github(False, "v1.0.0", None)
        assert len(calls) == 2

    def test_no_update_returns_none(self, monkeypatch):
        from module.update import detect

        def _fake_get(url, timeout=10, headers=None, proxies=None):
            return _FakeResp(200, self._release("v1.0.0"))

        monkeypatch.setattr("module.update.github_api.requests.get", _fake_get)
        assert detect._check_github(False, "v1.0.0", None) is None

    def test_prerelease_uses_first_entry(self, monkeypatch):
        from module.update import detect

        releases = [self._release("v2.1.0-rc1"), self._release("v2.1.0")]

        def _fake_get(url, timeout=10, headers=None, proxies=None):
            return _FakeResp(200, releases)

        monkeypatch.setattr("module.update.github_api.requests.get", _fake_get)
        info = detect._check_github(True, "v1.0.0", None)
        assert info.version == "v2.1.0-rc1"


class _FakeResp:
    def __init__(self, status_code, json_data):
        self.status_code = status_code
        self._json = json_data

    def json(self):
        return self._json
