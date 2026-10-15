"""Tests for the hello-world CLI entrypoint (issue #2 smoke test)."""

import subprocess
import sys
import unittest
from pathlib import Path

HELLO = Path(__file__).resolve().parent.parent / "hello.py"

EXPECTED_OUTPUT = "Hello from the factory!\n"


class HelloCLITest(unittest.TestCase):
    def test_prints_expected_output_once_and_exits_zero(self):
        result = subprocess.run(
            [sys.executable, str(HELLO)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.stdout, EXPECTED_OUTPUT)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
