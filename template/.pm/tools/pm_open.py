"""Open the project's board or map in a browser, starting it once. Standard library only.

Usage: python .pm/tools/pm_open.py {board|map} [--download]

The project root is the folder that holds .pm/, and the tool lives in .pm/tools/. The command, its arguments and the
port come from the project's .claude/launch.json, which the installer writes. Without that file the board runs
`backlog browser --no-open --port 6420`, and the map has no default: it is an optional layer.

A port that already answers is opened, never started a second time. The server outlives this command: it gets a
console window of its own on Windows and its own session elsewhere, with its output in .pm/local/open-<name>.log.
"""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

WAIT_SECONDS = 30  # how long a server may take to answer on its port
POLL_SECONDS = 0.5
ADDRESS = "http://127.0.0.1:{port}"
LOG = "open-{name}.log"  # under .pm/local/; holds the server's own output
# Without .claude/launch.json: the board's own command, and no map at all, since the map is an optional layer.
DEFAULTS = {"board": (["backlog", "browser", "--no-open", "--port", "6420"], 6420)}
INSTALL = {
    "backlog": "install it with `npm i -g backlog.md`.",
    "npx": "install Node.js from https://nodejs.org, which brings npx.",
}


def find_root(start):
    """The project root holds .pm/; the tools live in <root>/.pm/tools."""
    for folder in [start, *start.parents]:
        if (folder / ".pm").is_dir():
            return folder
    return start.parent


ROOT = find_root(Path(__file__).resolve().parent)


def configurations(root):
    """The entries of .claude/launch.json; empty when the file is missing or unreadable."""
    try:
        data = json.loads((root / ".claude" / "launch.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    found = data.get("configurations") if isinstance(data, dict) else None
    return [item for item in found if isinstance(item, dict)] if isinstance(found, list) else []


def port_of(command, given):
    """The port to wait on: the entry's `port` field, else the number after --port; 0 when neither is there."""
    if isinstance(given, int) and given > 0:
        return given
    if "--port" in command[:-1]:
        number = command[command.index("--port") + 1]
        return int(number) if number.isdigit() else 0
    return 0


def entry(root, name):
    """(command, port) for board or map, from .claude/launch.json, else the default, else None (no map installed)."""
    for config in configurations(root):
        executable, arguments = config.get("runtimeExecutable"), config.get("runtimeArgs")
        if config.get("name") != name or not executable or not isinstance(arguments, list):
            continue
        command = [str(executable), *(str(argument) for argument in arguments)]
        port = port_of(command, config.get("port"))
        if port:
            return command, port
    return DEFAULTS.get(name)


def listening(port):
    """True when something already answers on 127.0.0.1 at that port."""
    with socket.socket() as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def downloaded(package):
    """True when npx already holds the pinned package: `npx --no-install <package> --version` answers."""
    program = shutil.which("npx") or "npx"  # the full path: Windows cannot start npx.cmd by its bare name
    command = [program, "--no-install", package, "--version"]
    try:
        return subprocess.run(command, capture_output=True, timeout=120).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def start(command, root, log):
    """Run the command in the project root as its own process, so it outlives this command."""
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("wb") as output:  # closed here after the start: the child holds its own handle
        options = {"stdin": subprocess.DEVNULL, "stdout": output, "stderr": subprocess.STDOUT}
        if os.name == "nt":
            return subprocess.Popen(command, cwd=root, creationflags=subprocess.CREATE_NEW_CONSOLE, **options)
        return subprocess.Popen(command, cwd=root, start_new_session=True, **options)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="pm_open.py",
        description="Open the board or the map in your browser, starting it first when it is not running.",
        epilog=(
            "board: the task board.\n"
            "map: the architecture map, an optional layer added with `python .pm/tools/pm_init.py --map`.\n"
            "  --download: map only; allows the first start to download LikeC4 from npm."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("name", choices=("board", "map"), metavar="board|map", help="what to open")
    parser.add_argument("--download", action="store_true", help="map only: let the first start download LikeC4")
    args = parser.parse_args(argv)

    found = entry(ROOT, args.name)
    if found is None:
        if (ROOT / ".agents" / "skills" / "pm-likec4-dsl").is_dir():  # the map layer's skill: the layer is there
            print(
                "The map layer is installed, but .claude/launch.json has no `map` entry to start it; upgrading the "
                "package adds the entry (see the upgrade guide). Nothing was started."
            )
        else:
            print(
                "The map is not installed: it is an optional layer, added with "
                "`python .pm/tools/pm_init.py --map`. Nothing was started."
            )
        return 1
    command, port = found
    address = ADDRESS.format(port=port)
    if listening(port):
        # Only a port is known to answer, not which program holds it, so say both possibilities.
        print(f"Something already answers at {address}; nothing was started and I opened it in your browser.")
        print(
            f"If that page is not the {args.name}, another program holds port {port}: stop it, or change the port in "
            ".claude/launch.json."
        )
        webbrowser.open(address)
        return 0
    program = shutil.which(command[0])
    if program is None:
        print(
            f"The {args.name} needs `{command[0]}`, which this machine does not have: "
            f"{INSTALL.get(command[0], 'install it, then run this command again.')} Nothing was started."
        )
        return 1
    if args.name == "map" and Path(command[0]).stem.lower() == "npx" and not args.download:
        # Whatever the entry names (pinned or not), npx would fetch it: the first argument that is not a flag.
        package = next((argument for argument in command[1:] if not argument.startswith("-")), "likec4")
        if not downloaded(package):
            print(f"The map is not downloaded yet: LikeC4 comes from npm, and this machine has no copy of {package}.")
            print("Nothing was started. After the owner says yes, run: python .pm/tools/pm_open.py map --download")
            return 2
        # Without a yes the start itself must not download either: npx gets --no-install instead of -y.
        command = [
            command[0],
            "--no-install",
            *(argument for argument in command[1:] if argument not in ("-y", "--yes")),
        ]

    log = ROOT / ".pm" / "local" / LOG.format(name=args.name)
    process = start([program, *command[1:]], ROOT, log)
    deadline = time.monotonic() + WAIT_SECONDS
    while not listening(port):
        if process.poll() is not None:  # it stopped before it answered: waiting longer would not help
            print(f"The {args.name} stopped before it answered at {address} (exit code {process.returncode}).")
            print(f"I ran `{' '.join(command)}`; its output is in {log.relative_to(ROOT).as_posix()}.")
            print("Read that file, then run this command again.")
            return 1
        if time.monotonic() > deadline:
            print(f"The {args.name} did not answer at {address} within {WAIT_SECONDS} seconds.")
            print(f"I ran `{' '.join(command)}`; its output is in {log.relative_to(ROOT).as_posix()}.")
            print("Read that file, then run this command again.")
            return 1
        time.sleep(POLL_SECONDS)
    if process.poll() is not None:  # the port answers, but what this command started has quit: someone else answers
        print(
            f"Something answers at {address}, but the {args.name} I started stopped (exit code {process.returncode})."
        )
        print(
            f"Another program may hold port {port}; the {args.name}'s output is in {log.relative_to(ROOT).as_posix()}."
        )
        return 1
    webbrowser.open(address)
    print(f"The {args.name} is open at {address}")
    print(f"Command: {' '.join(command)}")
    if os.name == "nt":
        print("To stop it, close the window it opened.")
    else:
        print(f"To stop it, stop the process with id {process.pid}.")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            pass
    sys.exit(main())
