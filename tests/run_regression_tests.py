import pathlib
import sys
import unittest


def main():
    test_root = pathlib.Path(__file__).resolve().parent
    suite = unittest.defaultTestLoader.discover(str(test_root), pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
