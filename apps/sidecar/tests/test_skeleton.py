import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docgraph_sidecar import __version__


class SkeletonTest(unittest.TestCase):
    def test_version_is_defined(self) -> None:
        self.assertEqual(__version__, "0.0.0")


if __name__ == "__main__":
    unittest.main()
