import tempfile
import unittest
from pathlib import Path

from shelf import store


class StoreTest(unittest.TestCase):
    def test_add_then_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "books.json"
            store.add("Dune", path)
            self.assertEqual(store.load(path), [{"title": "Dune"}])


if __name__ == "__main__":
    unittest.main()
