"""Command line: python -m shelf.cli add TITLE | list"""

import argparse

from shelf import store


def main(argv=None):
    parser = argparse.ArgumentParser(prog="shelf")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    add = sub.add_parser("add")
    add.add_argument("title")
    args = parser.parse_args(argv)
    if args.command == "add":
        store.add(args.title)
    for book in store.load():
        print(book["title"])


if __name__ == "__main__":
    main()
