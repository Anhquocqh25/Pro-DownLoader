from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from reclip_desktop.updater import (
    _is_version_newer,
    check_for_updates,
    is_git_repository,
    get_local_git_commit,
    perform_one_click_update,
)


class TestUpdater(unittest.TestCase):
    def test_version_comparison(self):
        self.assertTrue(_is_version_newer("1.2.1", "1.2.0"))
        self.assertTrue(_is_version_newer("2.0.0", "1.9.9"))
        self.assertTrue(_is_version_newer("1.3.0", "1.2.9"))
        self.assertFalse(_is_version_newer("1.2.0", "1.2.0"))
        self.assertFalse(_is_version_newer("1.1.9", "1.2.0"))

    def test_git_repository_check(self):
        # We are inside a git repo
        self.assertTrue(is_git_repository())

    def test_get_local_git_commit(self):
        commit = get_local_git_commit()
        self.assertTrue(len(commit) >= 4)

    @patch("urllib.request.urlopen")
    def test_check_for_updates_available(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = (
            b'{"tag_name": "v9.9.9", "name": "Version 9.9.9", "body": "New feature", "assets": []}'
        )
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        info = check_for_updates()
        self.assertTrue(info["update_available"])
        self.assertEqual(info["latest_version"], "9.9.9")

    @patch("urllib.request.urlopen")
    def test_check_for_updates_up_to_date(self, mock_urlopen):
        mock_resp = MagicMock()
        # Mock same version and mock commit check to return local sha
        mock_resp.read.return_value = (
            b'{"tag_name": "v1.2.0", "name": "Version 1.2.0", "body": "Release", "sha": "1234567"}'
        )
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        with patch("reclip_desktop.updater.get_local_git_commit", return_value="1234567"):
            info = check_for_updates()
            self.assertFalse(info["update_available"])


if __name__ == "__main__":
    unittest.main()
