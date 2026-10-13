"""T01 acceptance: the replydesk package is importable."""

import unittest


class TestScaffold(unittest.TestCase):
    def test_package_imports(self):
        import replydesk

        self.assertTrue(replydesk.__doc__)


if __name__ == "__main__":
    unittest.main()
