"""Tests for everything that doesn't need a screen. Run: python3 -m unittest"""

import importlib
import os
import tempfile
import time
import unittest


class Core(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["KIOSKLOCK_HOME"] = self.tmp.name
        import kiosklock.store as store
        self.store = importlib.reload(store)

    def tearDown(self):
        self.tmp.cleanup()

    def test_password_is_hashed_and_checked(self):
        self.assertFalse(self.store.has_password())
        self.store.set_password("correct horse")
        self.assertTrue(self.store.check_password("correct horse"))
        self.assertFalse(self.store.check_password("wrong"))
        on_disk = (self.store.CONFIG_PATH).read_text()
        self.assertNotIn("correct horse", on_disk)
        self.assertEqual(oct(os.stat(self.store.CONFIG_PATH).st_mode & 0o777), "0o600")

    def test_lock_expires(self):
        self.store.save_lock("https://example.com", ["example.com"], time.time() + 60, "hi")
        self.assertEqual(self.store.active_lock()["url"], "https://example.com")
        self.store.save_lock("https://example.com", ["example.com"], time.time() - 1, "hi")
        self.assertIsNone(self.store.active_lock())
        self.store.clear_lock()
        self.store.clear_lock()  # clearing twice is fine

    def test_sidebar_escapes_message(self):
        from kiosklock import sidebar
        page = sidebar.render({"url": "https://a.com", "allowed_hosts": ["a.com"], "until": time.time() + 60,
                               "started": time.time(), "message": "<script>x</script>"})
        self.assertIn("&lt;script&gt;x&lt;/script&gt;", page)
        self.assertIn('data-url="https://a.com/"', page)

    def test_host_rules(self):
        from kiosklock.lockscreen import host_allowed
        self.assertTrue(host_allowed("leetcode.com", ["leetcode.com"]))
        self.assertTrue(host_allowed("assets.leetcode.com", ["leetcode.com"]))
        self.assertFalse(host_allowed("notleetcode.com", ["leetcode.com"]))
        self.assertFalse(host_allowed("leetcode.com.evil.io", ["leetcode.com"]))
        from kiosklock.cli import _default_host
        self.assertEqual(_default_host("https://www.wikipedia.org/wiki/Mac"), "wikipedia.org")


if __name__ == "__main__":
    unittest.main()
