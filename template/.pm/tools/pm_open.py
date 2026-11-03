"""Open this project's board or map, and keep a list of every project opened this way. Standard library only.

Usage: python .pm/tools/pm_open.py board|map [--download]
       python .pm/tools/pm_open.py stop board|map
       python .pm/tools/pm_open.py list
       python .pm/tools/pm_open.py opening ask|always|never

The project root is the folder that holds .pm/, and the tool lives in .pm/tools/. The command, its arguments and the
port come from the project's .claude/launch.json, which the installer writes; that file is only ever read. Without it
the board runs `backlog browser --no-open --port 6420`, and the map has no default: it is an optional layer.

The project list in ~/.pm/projects.json (or the folder PM_HOME names) is what lets several projects run at once. It
holds one entry per project, keyed by its resolved folder: the port of each server, the process id this tool started,
and the map's HMR port. A project joins it the first time this command opens something in it.

A port that answers is not proof that the server is ours. The board is asked for its /api/status project path; the map
is ours only while the process id recorded for that port still runs. Anything else is foreign: this project's own
server then starts on the first free port above.

The servers outlive this command: no console window on Windows, their own session elsewhere, with their output in
.pm/local/open-<name>.log. `stop` ends the one this tool started, with the processes it started.
"""

import argparse
import ctypes
import http.client
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import webbrowser
from pathlib import Path

WAIT_SECONDS = 30  # how long a server may take to answer on its port
POLL_SECONDS = 0.5
STATUS_TIMEOUT = 2  # a board answers /api/status at once; a slower answer is not the board we can trust
ADDRESS = "http://127.0.0.1:{port}"
LOG = "open-{name}.log"  # under .pm/local/; holds the server's own output
PORTS_TRIED = 50  # how many ports a taken first choice may push us up
HMR_FIRST = 24678  # the map's HMR port counts up from here; two maps may not share one
STILL_ACTIVE = 259  # GetExitCodeProcess answers this while the process runs
QUERY_LIMITED = 0x1000  # PROCESS_QUERY_LIMITED_INFORMATION: ask about a process without the right to end it
TASKKILL_SECONDS = 10
# Without .claude/launch.json: the board's own command, and no map at all, since the map is an optional layer.
DEFAULTS = {"board": (["backlog", "browser", "--no-open", "--port", "6420"], 6420)}
INSTALL = {
    "backlog": "install it with `npm i -g backlog.md`.",
    "npx": "install Node.js from https://nodejs.org, which brings npx.",
}
# .claude/launch.json entries may name either; the installer writes the first of each pair.
ENTRY_NAMES = {"board": "board", "backlog-board": "board", "map": "map", "likec4": "map"}
OPENINGS = ("ask", "always", "never")
OPENING_MEANINGS = {
    "ask": "at session start the agent asks once whether to open the board.",
    "always": "at session start the agent opens the board without asking.",
    "never": "at session start the agent does not offer the project window.",
}
# The one line `pm_board.py --resume` prints about the window; `never` prints nothing.
WINDOW_LINES = {
    "ask": "Project window: ask the user once whether to open the board (python .pm/tools/pm_open.py board).",
    "always": "Project window: the user chose always; open the board now with python .pm/tools/pm_open.py board.",
    "never": "",
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
        if ENTRY_NAMES.get(str(config.get("name", "")).casefold()) != name:
            continue
        if not executable or not isinstance(arguments, list):
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


def project_of(port):
    """The folder the board at that port says it serves: its /api/status projectPath, else None.

    Nothing usable answers covers all three cases the caller must treat as not ours: no answer at all, an answer that
    is not JSON, and JSON without a project path.
    """
    try:
        with urllib.request.urlopen(ADDRESS.format(port=port) + "/api/status", timeout=STATUS_TIMEOUT) as answer:
            data = json.loads(answer.read().decode("utf-8", "replace"))
    except (OSError, ValueError, http.client.HTTPException):
        return None
    path = data.get("projectPath") if isinstance(data, dict) else None
    return str(path) if path else None


def folder_key(folder):
    """A project's name in the project list: its resolved path, written with forward slashes."""
    try:
        path = Path(folder).resolve()
    except (OSError, RuntimeError):
        path = Path(os.path.abspath(str(folder)))
    return path.as_posix()


def same_key(left, right):
    """Two keys name the same folder; Windows paths compare without their case."""
    return os.path.normcase(left) == os.path.normcase(right)


def same_folder(left, right):
    """True when both name the same folder, compared as resolved paths (case-insensitive on Windows)."""
    return bool(left) and bool(right) and same_key(folder_key(left), folder_key(right))


def store_dir():
    """The folder holding the project list: the PM_HOME folder when set (tests use it), else ~/.pm."""
    home = os.environ.get("PM_HOME")
    return Path(home) if home else Path.home() / ".pm"


def store_path():
    return store_dir() / "projects.json"


def read_store():
    """The project list: {"opening": ..., "projects": {<folder>: {...}}}. A missing or broken file reads as empty."""
    try:
        data = json.loads(store_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    projects = data.get("projects")
    data["projects"] = {}
    if isinstance(projects, dict):
        data["projects"] = {key: value for key, value in projects.items() if isinstance(value, dict)}
    return data


def write_store(data):
    """Write the project list atomically: a temporary file next to it, then os.replace. False when that failed."""
    folder, temporary = store_dir(), None
    try:
        folder.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=str(folder), prefix="projects-", suffix=".json")
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            json.dump(data, out, indent=2, sort_keys=True)
            out.write("\n")
        os.replace(temporary, store_path())
        return True
    except OSError:
        if temporary:
            Path(temporary).unlink(missing_ok=True)
        return False


def warn_store():
    """One plain line: the ports and process ids are not remembered, but the server still runs."""
    print(f"I could not write the project list at {store_path()}; the ports and process ids are not remembered.")


def record_of(data, folder):
    """This project's entry in the project list, found the way the list is keyed; empty when it has none yet."""
    key = folder_key(folder)
    found = [
        record for name, record in data.get("projects", {}).items() if same_key(name, key) and isinstance(record, dict)
    ]
    return found[0] if found else {}


def server_of(data, folder, name):
    """The recorded board or map of this project: {"port": ..., "pid": ...}, or {} when there is none."""
    server = record_of(data, folder).get(name)
    return server if isinstance(server, dict) else {}


def other_ports(data, folder):
    """Every port another registered project holds, so two projects never take the same one."""
    mine, ports = folder_key(folder), set()
    for key, record in data.get("projects", {}).items():
        if same_key(key, mine):
            continue
        for server in record.values():
            if isinstance(server, dict):
                ports.update(value for value in (server.get("port"), server.get("hmr_port")) if isinstance(value, int))
    return ports


def save(data, folder, name, port, pid=None, hmr=None):
    """Record one server of this project and write the list: its port, the process id, the map's HMR port."""
    key, projects = folder_key(folder), data.setdefault("projects", {})
    record = projects.setdefault(next((item for item in projects if same_key(item, key)), key), {})
    record["name"] = Path(folder).name
    server = {"port": port}
    if pid:
        server["pid"] = pid
    if hmr:
        server["hmr_port"] = hmr
    record[name] = server
    return write_store(data)


def opening(data=None):
    """The stored opening setting; a missing or unknown value reads as ask."""
    value = (read_store() if data is None else data).get("opening")
    return value if value in OPENINGS else OPENINGS[0]


def choose_port(wanted, used):
    """`wanted` when it is free, else the first free port above it; 0 when the 50 tried ports are all taken."""
    if not isinstance(wanted, int) or wanted <= 0:
        return 0
    for port in range(wanted, wanted + PORTS_TRIED):
        if port not in used and not listening(port):
            return port
    return 0


def port_for(data, folder, name, wanted):
    """The port to try: the one this project recorded, else the launch.json port, else the first free one above it."""
    recorded = server_of(data, folder, name).get("port")
    if isinstance(recorded, int) and recorded > 0:
        return recorded
    used = other_ports(data, folder)
    if isinstance(wanted, int) and wanted > 0 and wanted not in used:
        return wanted
    return choose_port(wanted, used)


def hmr_for(data, folder):
    """The map's HMR port: the recorded one while it is still free, else the first free one from 24678 up."""
    used = other_ports(data, folder)
    recorded = server_of(data, folder, "map").get("hmr_port")
    if isinstance(recorded, int) and recorded not in used and not listening(recorded):
        return recorded
    return choose_port(HMR_FIRST, used)


def alive(pid):
    """True while that process runs. Nothing is ended: os.kill ends a process on Windows, so ctypes asks there."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        return alive_on_windows(pid)
    try:
        os.kill(pid, 0)  # signal 0 only asks whether the process exists
    except ProcessLookupError:
        return False
    except OSError:
        return True  # no permission to signal it, so it exists
    return True


def alive_on_windows(pid):
    """OpenProcess plus GetExitCodeProcess: still 259 while it runs, and no right to end it is asked for."""
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.restype = ctypes.c_void_p
    handle = kernel32.OpenProcess(QUERY_LIMITED, False, pid)
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code)):
            return False
        return code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(ctypes.c_void_p(handle))


def terminate(pid):
    """End a process this tool started together with the ones it started; True when the system did it."""
    if os.name == "nt":
        # taskkill /T: npx starts node under cmd, so the whole tree has to go.
        command = ["taskkill", "/T", "/F", "/PID", str(pid)]
        try:
            return subprocess.run(command, capture_output=True, timeout=TASKKILL_SECONDS).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)  # the group the server got when it started
    except OSError:
        return False
    return True


def with_port(command, port):
    """The same command with `--port <port>`: the value after it replaced, or the flag added."""
    arguments = list(command)
    if "--port" in arguments[:-1]:
        arguments[arguments.index("--port") + 1] = str(port)
    else:
        arguments += ["--port", str(port)]
    return arguments


def board_command(command):
    """The board command with --non-interactive: its server has no window in which to ask anything."""
    if Path(command[0]).stem.casefold() != "backlog" or "browser" not in command[1:]:
        return list(command)
    if "--non-interactive" in command:
        return list(command)
    return [*command, "--non-interactive"]


def map_command(command, hmr):
    """The map command on this machine only, with its own HMR port so two maps never collide."""
    arguments = list(command)
    if "--listen" not in arguments:
        arguments += ["--listen", "127.0.0.1"]
    if "--hmr-port" not in arguments:
        arguments += ["--hmr-port", str(hmr)]
    return arguments


def start(command, root, log):
    """Run the command in the project root as its own process, so it outlives this command."""
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("wb") as output:  # closed here after the start: the child holds its own handle
        options = {"stdin": subprocess.DEVNULL, "stdout": output, "stderr": subprocess.STDOUT}
        if os.name == "nt":
            # No console window to close, so the server belongs to no window and writes to the log alone. The two
            # flags exist on Windows only; a test that fakes os.name elsewhere reads 0.
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            return subprocess.Popen(command, cwd=root, creationflags=flags, **options)
        return subprocess.Popen(command, cwd=root, start_new_session=True, **options)


def downloaded(package):
    """True when npx already holds the pinned package: `npx --no-install <package> --version` answers."""
    program = shutil.which("npx") or "npx"  # the full path: Windows cannot start npx.cmd by its bare name
    command = [program, "--no-install", package, "--version"]
    try:
        return subprocess.run(command, capture_output=True, timeout=120).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def relative_log(log):
    """The log's path as the project sees it, so the line can be copied into a command."""
    try:
        return log.relative_to(ROOT).as_posix()
    except ValueError:
        return log.as_posix()


def missing_entry_message(name):
    """Why the map has no command to start, in words for the person who asked for it."""
    if (ROOT / ".agents" / "skills" / "pm-likec4-dsl").is_dir():  # the map layer's skill: the layer is there
        return (
            "The map layer is installed, but .claude/launch.json has no `map` entry to start it; upgrading the "
            "package adds the entry (see the upgrade guide). Nothing was started."
        )
    return (
        "The map is not installed: it is an optional layer, added with "
        "`python .pm/tools/pm_init.py --map`. Nothing was started."
    )


def no_port_message(what, first):
    """One plain line when every port this project could use is taken; nothing was started."""
    return f"The {PORTS_TRIED} ports from {first} up are all taken, so {what} was not started. Free one of them."


def foreign_line(name, port, served):
    """One plain line: something answers there, and it does not answer for this project."""
    who = f"another project ({served})" if served else "another program"
    return f"Port {port} answers for {who}, so this project's {name} starts on a free port above."


def wait_for_board(port, folder, deadline):
    """The folder the board at that port names last: asked until it names this project's, or the time runs out."""
    served = project_of(port)
    while not same_folder(served, folder) and time.monotonic() <= deadline:
        time.sleep(POLL_SECONDS)
        served = project_of(port)
    return served


def open_server(name, download=False):
    """Open this project's board or map, starting it here when it is not this project's own server yet."""
    data = read_store()
    found = entry(ROOT, name)
    if found is None:
        print(missing_entry_message(name))
        return 1
    command, wanted = found
    port = port_for(data, ROOT, name, wanted)
    hmr = hmr_for(data, ROOT) if name == "map" else None
    if not port:
        print(no_port_message(f"the {name}", wanted))
        return 1
    if name == "map" and not hmr:
        print(no_port_message("the map's HMR port", HMR_FIRST))
        return 1
    address = ADDRESS.format(port=port)
    if listening(port):
        served = project_of(port) if name == "board" else None
        ours = same_folder(served, ROOT) if name == "board" else map_is_ours(data, port)
        if ours:
            print(f"The {name} is already running at {address}; I opened it in your browser.")
            webbrowser.open(address)
            if name == "board":
                keep(data, port)
            return 0
        # The port answers for another program or another project: ours goes above it, as a new port would.
        print(foreign_line(name, port, served))
        answered = port
        port = choose_port(port, other_ports(data, ROOT))
        if not port:
            print(no_port_message(f"the {name}", answered))
            return 1
        address = ADDRESS.format(port=port)

    command = with_port(command, port)
    command = board_command(command) if name == "board" else map_command(command, hmr)
    program = shutil.which(command[0])
    if program is None:
        print(
            f"The {name} needs `{command[0]}`, which this machine does not have: "
            f"{INSTALL.get(command[0], 'install it, then run this command again.')} Nothing was started."
        )
        return 1
    if name == "map" and Path(command[0]).stem.casefold() == "npx" and not download:
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

    log = ROOT / ".pm" / "local" / LOG.format(name=name)
    process = start([program, *command[1:]], ROOT, log)
    if not save(data, ROOT, name, port, pid=process.pid, hmr=hmr):
        warn_store()
    deadline, ran = time.monotonic() + WAIT_SECONDS, " ".join(command)
    while not listening(port):
        if process.poll() is not None:  # it stopped before it answered: waiting longer would not help
            print(f"The {name} stopped before it answered at {address} (exit code {process.returncode}).")
            print(f"I ran `{ran}`; its output is in {relative_log(log)}.")
            print("Read that file, then run this command again.")
            return 1
        if time.monotonic() > deadline:
            print(f"The {name} did not answer at {address} within {WAIT_SECONDS:g} seconds.")
            print(f"I ran `{ran}`; its output is in {relative_log(log)}.")
            print("Read that file, then run this command again.")
            return 1
        time.sleep(POLL_SECONDS)
    if process.poll() is not None:  # the port answers, but what this command started has quit: someone else answers
        print(f"Something answers at {address}, but the {name} I started stopped (exit code {process.returncode}).")
        print(f"Another program may hold port {port}; the {name}'s output is in {relative_log(log)}.")
        return 1
    if name == "board":
        served = wait_for_board(port, ROOT, deadline)  # a port that answers is not proof: the board must name us
        if not same_folder(served, ROOT):
            print(
                f"Something answers at {address}, but it is not this project's board; it serves {served or 'nothing'}."
            )
            print(f"The board I started writes to {relative_log(log)}; read that file, then run this command again.")
            return 1
    webbrowser.open(address)
    print(f"The {name} is open at {address}")
    print(f"Command: {ran}")
    print(f"To stop it, run: python .pm/tools/pm_open.py stop {name}")
    return 0


def map_is_ours(data, port):
    """The map has no status endpoint: ours only while the process recorded for that port still runs."""
    server = server_of(data, ROOT, "map")
    return server.get("port") == port and alive(server.get("pid"))


def keep(data, port):
    """Remember a board that was already running: its port, and its process id while that one still runs."""
    pid = server_of(data, ROOT, "board").get("pid")
    if not alive(pid):
        pid = None  # this tool did not start it, so its process id is not ours to stop later
    if not save(data, ROOT, "board", port, pid=pid):
        warn_store()


def stop_server(name):
    """Stop the server this tool started for this project, and nothing else."""
    data = read_store()
    server = server_of(data, ROOT, name)
    pid = server.get("pid")
    if not server:
        print(f"No {name} is recorded for this project, so I stopped nothing.")
        return 0
    if not pid or not alive(pid):
        print(f"The {name} recorded for this project is not running, so I stopped nothing.")
        return 0
    if not terminate(pid):
        print(f"I could not stop the {name} (process id {pid}); it may already have stopped. Nothing else was touched.")
        return 1
    # The port stays, so this project keeps its address; only the claim to a running process goes.
    record_of(data, ROOT)[name] = {key: value for key, value in server.items() if key != "pid"}
    if not write_store(data):
        warn_store()
    print(f"Stopped the {name} (process id {pid}).")
    return 0


def show_list():
    """One line per registered project: its folder, then the address of its board and map and whether each runs."""
    projects = read_store().get("projects", {})
    if not projects:
        print("No project is registered yet: `python .pm/tools/pm_open.py board` adds this one to the list.")
        return 0
    for key in sorted(projects):
        record = projects[key]
        name = record.get("name") or Path(key).name
        states = " · ".join(server_state(server, record.get(server)) for server in ("board", "map"))
        print(f"{name} ({key}) · {states}")
    return 0


def server_state(name, server):
    """`board http://127.0.0.1:6421 running`, or `map not started yet`."""
    port = server.get("port") if isinstance(server, dict) else None
    if not isinstance(port, int) or port <= 0:
        return f"{name} not started yet"
    running = alive(server.get("pid")) if server.get("pid") else listening(port)
    return f"{name} {ADDRESS.format(port=port)} {'running' if running else 'stopped'}"


def set_opening(value):
    """Store the opening choice in the project list and say what it means."""
    data = read_store()
    data["opening"] = value
    if not write_store(data):
        warn_store()
        return 1
    print(f"The project window is now '{value}': {OPENING_MEANINGS[value]}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="pm_open.py",
        description="Open this project's board or map in your browser, list the projects opened this way, or stop one.",
        epilog=(
            "board: the task board of this project.\n"
            "map: the architecture map, an optional layer added with `python .pm/tools/pm_init.py --map`.\n"
            "  --download: map only; allows the first start to download LikeC4 from npm.\n"
            "stop board|map: stop the server this tool started for this project.\n"
            "list: every project opened this way, with its board and map and whether they run.\n"
            "opening ask|always|never: whether a session start offers the project window (the default is ask)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "name",
        choices=("board", "map", "stop", "list", "opening"),
        metavar="board|map|stop|list|opening",
        help="what to do",
    )
    parser.add_argument("value", nargs="?", help="stop: board or map; opening: ask, always or never")
    parser.add_argument("--download", action="store_true", help="map only: let the first start download LikeC4")
    args = parser.parse_args(argv)

    if args.name == "list":
        return show_list()
    if args.name == "stop":
        if args.value not in ("board", "map"):
            print("Say what to stop: `python .pm/tools/pm_open.py stop board` or `... stop map`.")
            return 1
        return stop_server(args.value)
    if args.name == "opening":
        if args.value not in OPENINGS:
            print("Say how to open: `python .pm/tools/pm_open.py opening ask`, `always` or `never`.")
            return 1
        return set_opening(args.value)
    if args.value:
        print(f"`{args.name}` takes no other word; run `python .pm/tools/pm_open.py --help` to see the commands.")
        return 1
    return open_server(args.name, args.download)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            pass
    sys.exit(main())
