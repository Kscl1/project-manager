"""Load and save the reading list as one JSON file."""

import json
from pathlib import Path

DEFAULT_PATH = Path("books.json")


def load(path=DEFAULT_PATH):
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def add(title, path=DEFAULT_PATH):
    books = load(path)
    books.append({"title": title})
    path.write_text(json.dumps(books, indent=2), encoding="utf-8")
    return books
