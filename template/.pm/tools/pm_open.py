"""Open this project's board or map, and keep a list of every project opened this way. Standard library only.

Usage: python .pm/tools/pm_open.py board|map [--download]
       python .pm/tools/pm_open.py stop board|map
       python .pm/tools/pm_open.py list
       python .pm/tools/pm_open.py opening ask|always|never
       python .pm/tools/pm_open.py window
       python .pm/tools/pm_open.py stop window

`window` opens the project window (pm_bridge.py), started once for the whole machine, with this project on its list;
`stop window` ends it if this tool started it, and every server and agent keeps running.

--root names another project's folder and --no-browser leaves the browser alone: the project window (pm_bridge.py)
runs this tool that way, for any registered project.

The project root is the folder that holds .pm/, and the tool lives in .pm/tools/. The command, its arguments and the
port come from the project's .claude/launch.json, which the installer writes; that file is only ever read. Without it
the board runs `backlog browser --no-open --port 6420`, and the map has no default: it is an optional layer.

The project list in ~/.pm/projects.json (or the folder PM_HOME names) is what lets several projects run at once. It
holds one entry per project, keyed by its resolved folder: the port of each server, the map's HMR port, and the
process this tool started, with its id and the time it started. A project joins it the first time this command opens
something in it. A lock file next to the list lets one run at a time read it, choose ports and write it back; a run
that cannot take the lock changes nothing and says so, so two runs never write their old copy over each other.

A port that answers is not proof that the server is ours, and a running process id is not proof that it is our
process: the system hands the id out again once ours ends. The board is ours while its /api/status names this
project's folder; the map is ours while its port answers and the recorded process still started when it was recorded,
or while it serves the LikeC4 name in this project's map config, as one the Claude preview or a terminal started does.
Anything else is foreign: this project's own server then starts on the first free port above. A port counts as taken
when something answers on 127.0.0.1 or ::1.

The servers outlive this command: no console window on Windows, their own session elsewhere, with their output in
.pm/local/open-<name>.log. `stop` ends the one this tool started, with the processes it started.
"""

import argparse
import contextlib
import ctypes
import hashlib
import http.client
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

WINDOW_PORT = 7420  # pm_bridge.py's port; a bridge on another one is started by hand and not looked after here
WAIT_SECONDS = 30  # how long a server may take to answer on its port
POLL_SECONDS = 0.5
STATUS_TIMEOUT = 2  # a board answers /api/status at once; a slower answer is not the board we can trust
ADDRESS = "http://127.0.0.1:{port}"
LOOPBACKS = ("127.0.0.1", "::1")  # a port is taken when either answers there; the launcher itself runs on IPv4
LOG = "open-{name}.log"  # under .pm/local/; holds the server's own output
LOCK = "projects.lock"  # next to projects.json: one run at a time reads the list, chooses ports and writes it back
LOCK_WAIT = 10  # seconds to wait for another run to finish with the list
LOCK_STALE = 60  # a lock file older than this was left behind by a run that died
PORTS_TRIED = 50  # how many ports a taken first choice may push us up
HMR_FIRST = 24678  # the map's HMR port counts up from here; two maps may not share one
STILL_ACTIVE = 259  # GetExitCodeProcess answers this while the process runs
QUERY_LIMITED = 0x1000  # PROCESS_QUERY_LIMITED_INFORMATION: ask about a process without the right to end it
TASKKILL_SECONDS = 10
OURS, ANSWERS, STOPPED = "ours", "answers", "stopped"  # what the ownership check says about a port
WORDS = {OURS: "running", ANSWERS: "answers for another program", STOPPED: "stopped"}  # how `list` says it
# Without .claude/launch.json: the board's own command, and no map at all, since the map is an optional layer.
DEFAULTS = {"board": (["backlog", "browser", "--no-open", "--port", "6420"], 6420)}
INSTALL = {
    "backlog": "install it with `npm i -g backlog.md`.",
    "npx": "install Node.js from https://nodejs.org, which brings npx.",
}
# .claude/launch.json entries may name either; the installer writes the first of each pair.
ENTRY_NAMES = {"board": "board", "backlog-board": "board", "map": "map", "likec4": "map"}
# A running map is known by the `name` in its LikeC4 config: these are the config files LikeC4 reads as JSON.
LIKEC4_CONFIGS = (".likec4rc", ".likec4.config.json", "likec4.config.json")
# The LikeC4 dev server lists the projects it serves in a module of its Vite plugin, at this address. Its first line
# imports and names the module, so a page that only quotes one is not taken for it; each project's id is one line.
PROJECTS_PATH = "/@id/likec4:projects"
PROJECTS_MARK = '__vite__createHotContext("likec4:plugin/projects.js")'
SERVED_LIST = re.compile(r"^export const projects = \[(.*?)\];$", re.S | re.M)
SERVED_ID = re.compile(r'^\tid: ("(?:[^"\\]|\\.)*"),?$', re.M)
MADE_NAME = re.compile(r"(.+)-([0-9a-f]{6})")  # the name pm_init writes: the folder's name, then its path code
OPENINGS = ("ask", "always", "never")
OPENING_MEANINGS = {
    "ask": "at session start the agent asks once whether to open the board.",
    "always": "at session start the agent opens the board without asking.",
    "never": "at session start the agent does not offer the project window.",
}
# The one line `pm_board.py --resume` prints about the window; `never` prints nothing.
WINDOW_LINES = {
    "ask": "Project window: ask the user once whether to open the project window (python .pm/tools/pm_open.py window).",
    "always": "Project window: the user chose always; open the project window now with python .pm/tools/pm_open.py window.",
    "never": "",
}


def find_root(start):
    """The project root holds .pm/; the tools live in <root>/.pm/tools."""
    for folder in [start, *start.parents]:
        if (folder / ".pm").is_dir():
            return folder
    return start.parent


ROOT = find_root(Path(__file__).resolve().parent)
BROWSER = True  # --no-browser turns it off: the project window shows the map itself


def configurations(root):
    """The entries of .claude/launch.json; empty when the file is missing or unreadable."""
    try:
        data = json.loads((root / ".claude" / "launch.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    found = data.get("configurations") if isinstance(data, dict) else None
    return [item for item in found if isinstance(item, dict)] if isinstance(found, list) else []


def value_after(command, flag):
    """The number after that flag in the command, else 0."""
    if flag in command[:-1]:
        number = command[command.index(flag) + 1]
        return int(number) if number.isdigit() else 0
    return 0


def port_of(command, given):
    """The port to wait on: the entry's `port` field, else the number after --port; 0 when neither is there."""
    if isinstance(given, int) and given > 0:
        return given
    return value_after(command, "--port")


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


def answers(port):
    """True when something answers at that port on 127.0.0.1 or ::1.

    A machine without IPv6 answers nothing there, and a socket family the system does not have is just that.
    """
    if not isinstance(port, int) or port <= 0:
        return False
    return any(answers_on(address, port) for address in LOOPBACKS)


def answers_on(address, port):
    """True when something answers at that port on that one loopback; a refusal takes two seconds on Windows."""
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    try:
        with socket.socket(family) as probe:
            probe.settimeout(0.5)
            return probe.connect_ex((address, port)) == 0
    except OSError:
        return False  # no IPv6 on this machine, or no right to open a socket: no answer there


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


def map_folder(root, command):
    """The folder the map command serves: the path right after `start`, else the project root."""
    if "start" in command:
        after = command.index("start") + 1
        if after < len(command) and not command[after].startswith("-"):
            return Path(root) / command[after]
    return Path(root)


def map_name(root):
    """This project's map name: `name` in the first of the JSON configs in the folder its map serves, else None.

    The first config found is the one read, even when it cannot be: LikeC4 also reads comments and JSON5 there, which
    this does not, and taking the next file instead could pick a name that is not the map's.
    """
    found = entry(Path(root), "map")
    if found is None:
        return None
    folder = map_folder(root, found[0])
    for config in LIKEC4_CONFIGS:
        path = folder / config
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        name = data.get("name") if isinstance(data, dict) else None
        return name if isinstance(name, str) and name else None
    return None


def path_code(folder):
    """Six characters from the project's full path; pm_init.py puts the same code in the map name it writes."""
    return hashlib.sha256(os.path.normcase(str(Path(folder).resolve())).encode("utf-8")).hexdigest()[:6]


def made_here(folder, name):
    """False for a name pm_init made for another folder: a likec4.config.json that was copied or moved here.

    Such a name ends in the path code of the folder it was made for, whatever the folders are called, so a copy or a
    renamed folder would take the first folder's map for its own. A name the user chose carries no code and is taken
    as it is; one that only looks like ours (ends in six hex characters) is asked to carry this folder's code too.
    """
    made = MADE_NAME.fullmatch(name)
    return not made or made.group(2) == path_code(folder)


def served_maps(base):
    """The LikeC4 project names the server at that address serves; empty for anything that is not LikeC4's list."""
    place = urllib.parse.urlsplit(base)
    if not answers_on(place.hostname, place.port):
        return []  # asked first: the request alone would wait through a refusal
    try:
        with urllib.request.urlopen(base + PROJECTS_PATH, timeout=STATUS_TIMEOUT) as answer:
            text = answer.read().decode("utf-8", "replace")
    except (OSError, ValueError, http.client.HTTPException):
        return []  # nothing there, or not on this loopback
    head = text.split("\n", 1)[0]
    found = SERVED_LIST.search(text) if head.startswith("import ") and PROJECTS_MARK in head else None
    try:
        return [json.loads(quoted) for quoted in SERVED_ID.findall(found.group(1))] if found else []
    except ValueError:
        return []


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


def keep_broken(path):
    """Whether the project list may be replaced: a copy of a list that cannot be read is kept first.

    The list is read as bytes, so one that is not UTF-8 text counts as broken too, and its copy holds the very bytes
    that were there. True when the list reads fine, or when it is broken and its copy exists now; False when the copy
    cannot be made, and then the old file has to stand, since replacing it would leave no copy of the broken list.
    """
    try:
        original = path.read_bytes()
    except FileNotFoundError:
        return True  # no list yet, so there is nothing to keep
    except OSError as error:  # there, but this run may not read it: replacing it would lose what it holds
        print(f"The project list at {path} is there but could not be read ({error.strerror}); I left it as it was.")
        return False
    try:
        readable = isinstance(json.loads(original.decode("utf-8")), dict)
    except ValueError:  # not UTF-8, or not JSON
        readable = False
    if readable:
        return True
    try:
        shutil.copyfile(path, Path(f"{path}.broken"))
    except OSError:
        print(
            f"The project list at {path} could not be read, and its copy at {path}.broken could not be kept; "
            "I left the list as it was."
        )
        return False
    print(f"The project list at {path} could not be read; I kept a copy at {path}.broken and started a new one.")
    return True


def write_store(data):
    """Write the project list atomically: a temporary file next to it, then os.replace. False when that failed."""
    folder, temporary = store_dir(), None
    if not keep_broken(store_path()):  # before the file it copies is replaced
        return False
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


@contextlib.contextmanager
def locked():
    """Hold the project list's lock while it is read, ports are chosen and the result is written back.

    Yields True while the lock is held. The lock is a file next to the list, made with O_EXCL. A lock file older than
    LOCK_STALE was left behind by a run that died, so it is removed and taken. Windows refuses the same open with
    PermissionError while another run's lock file is being deleted, which is a busy lock too, so that answer is waited
    for like a lock file that is there. A run that still waits after LOCK_WAIT seconds, or cannot make the lock file at
    all, gets False and one plain line: such a run must not read, choose and write the list, or its old copy would
    overwrite what the other run wrote. Always released.
    """
    folder, handle, problem = store_dir(), None, ""
    lock = folder / LOCK
    deadline = time.monotonic() + LOCK_WAIT
    try:
        folder.mkdir(parents=True, exist_ok=True)
        while handle is None:
            try:
                handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except (FileExistsError, PermissionError):
                try:
                    age = time.time() - lock.stat().st_mtime
                except OSError:
                    age = 0  # released just now: try again, after the same wait and deadline check
                if age > LOCK_STALE:
                    lock.unlink(missing_ok=True)  # a run that died left it behind: take it now
                elif time.monotonic() > deadline:
                    problem = (
                        f"Another run is using the project list at {store_path()}; nothing was changed. "
                        "Run this command again in a moment."
                    )
                    break
                else:
                    time.sleep(0.05)
            except OSError:
                problem = (
                    f"I could not make the lock file at {lock}; nothing was changed. "
                    "Check that the folder can be written, then run this command again."
                )
                break
    except OSError:
        problem = (
            f"I could not make the folder for the project list at {folder}; nothing was changed. "
            "Check the folder, then run this command again."
        )
    try:
        if problem:
            print(problem)
        yield handle is not None
    finally:
        if handle is not None:
            os.close(handle)
            lock.unlink(missing_ok=True)


def record_of(data, folder):
    """This project's entry in the project list, found the way the list is keyed; empty when it has none yet."""
    key = folder_key(folder)
    for name, record in data.get("projects", {}).items():
        if same_key(name, key) and isinstance(record, dict):
            return record
    return {}


def server_of(data, folder, name):
    """The recorded board or map of this project: {"port": ..., "pid": ..., "started": ...}, or {} without one."""
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


def save(data, folder, name, port, pid=None, started=None, hmr=None):
    """Record one server of this project and write the list: its port, the process that runs it, the HMR port."""
    key, projects = folder_key(folder), data.setdefault("projects", {})
    record = projects.setdefault(next((item for item in projects if same_key(item, key)), key), {})
    record["name"] = Path(folder).name
    server = {"port": port}
    if pid:
        server["pid"] = pid
    if started:
        server["started"] = started
    if hmr:
        server["hmr_port"] = hmr
    record[name] = server
    return write_store(data)


def forget(data, folder, name):
    """Drop a recorded process that is not ours anymore: it ended, or its id belongs to another process now."""
    server = server_of(data, folder, name)
    if not server.get("pid") or process_of(server):
        return
    record_of(data, folder)[name] = {key: value for key, value in server.items() if key not in ("pid", "started")}
    if not write_store(data):
        warn_store()


def opening(data=None):
    """The stored opening setting; a missing or unknown value reads as ask."""
    value = (read_store() if data is None else data).get("opening")
    return value if value in OPENINGS else OPENINGS[0]


def choose_port(wanted, used):
    """`wanted` when it is free, else the first free port above it; 0 when the 50 tried ports are all taken."""
    if not isinstance(wanted, int) or wanted <= 0:
        return 0
    for port in range(wanted, wanted + PORTS_TRIED):
        if port not in used and not answers(port):
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


def hmr_for(data, folder, wanted):
    """The map's HMR port: the one the entry or the record names while it is free, else the first free one above."""
    used = other_ports(data, folder)
    for port in (wanted, server_of(data, folder, "map").get("hmr_port")):
        if isinstance(port, int) and port > 0 and port not in used and not answers(port):
            return port
    return choose_port(wanted if isinstance(wanted, int) and wanted > 0 else HMR_FIRST, used)


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


def start_time(pid):
    """When that process started, as text to keep in the list; None when that cannot be read (so it is not ours)."""
    if not isinstance(pid, int) or pid <= 0:
        return None
    if os.name == "nt":
        return start_on_windows(pid)
    if os.path.isdir("/proc"):
        return start_from_proc(pid)
    return start_from_ps(pid)


def start_on_windows(pid):
    """GetProcessTimes through the same query-only handle as alive_on_windows: the creation time, in filetime ticks."""
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.restype = ctypes.c_void_p
    handle = kernel32.OpenProcess(QUERY_LIMITED, False, pid)
    if not handle:
        return None
    try:
        clock = [ctypes.c_ulonglong() for _ in range(4)]  # created, exited, kernel time, user time
        asked = kernel32.GetProcessTimes(ctypes.c_void_p(handle), *(ctypes.byref(value) for value in clock))
        return str(clock[0].value) if asked else None
    finally:
        kernel32.CloseHandle(ctypes.c_void_p(handle))


def start_from_proc(pid):
    """Linux: the 22nd field of /proc/<pid>/stat counts clock ticks since the machine started."""
    try:
        text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    fields = text[text.rfind(")") + 1 :].split()  # the second field may hold spaces and brackets
    return fields[19] if len(fields) > 19 else None


def start_from_ps(pid):
    """Elsewhere: `ps -o lstart= -p <pid>` prints the start time of that process."""
    command = ["ps", "-o", "lstart=", "-p", str(pid)]
    try:
        answer = subprocess.run(command, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return answer.stdout.strip() or None


def process_of(server):
    """The process this tool started for that record, while it still runs and is still the same process: its id.

    A process id alone proves nothing: the system hands the id to another program once ours ends. The recorded start
    time is what tells the two apart, so a record without one, or an unreadable one, is not ours.
    """
    pid, started = server.get("pid"), server.get("started")
    if not started or not alive(pid):
        return None
    return pid if start_time(pid) == str(started) else None


def ownership(folder, name, server, port):
    """(state, served, address): whether this project's server at that port is ours and running, for open, list, stop.

    state is OURS, ANSWERS (the port answers, but not for this project's own server) or STOPPED (nothing answers
    there). served says what the server there names, when it names something: a board's folder, a map's LikeC4
    projects. The board is ours while its status names this folder. The map is ours while its recorded process is
    still the one we started, or while it serves this project's map name on one loopback; address is where a browser
    reaches it, which for a map someone else started may be ::1 alone.
    """
    address = ADDRESS.format(port=port)
    if not isinstance(port, int) or port <= 0:
        return STOPPED, None, address
    if name == "board":
        served = project_of(port)
        if same_folder(served, folder):
            return OURS, served, address
        return (ANSWERS if answers(port) else STOPPED), served, address
    if not answers(port):
        return STOPPED, None, address
    if process_of(server):
        return OURS, None, address
    # A map this tool did not start (the Claude preview, a terminal) is this project's when it serves its name. Each
    # loopback is asked on its own: 127.0.0.1 and ::1 may be two different programs on the same port.
    own, served = map_name(folder), []
    for base in (address, f"http://[::1]:{port}"):
        names = served_maps(base)
        if own and own in names and made_here(folder, own):
            return OURS, None, base
        served += [item for item in names if item not in served]
    return ANSWERS, (f"the LikeC4 project {', '.join(served)}" if served else None), address


def own_group(pid):
    """True when that process leads the process group `start()` gave it: its own id is the group's id.

    The servers start with `start_new_session=True`, so a server's group is its own. Another group id means the id now
    belongs to a process that this tool did not start, and ending that group would end other programs.
    """
    if os.name == "nt":
        return True  # no group to signal there: taskkill /T ends the tree by itself
    try:
        return os.getpgid(pid) == pid
    except OSError:
        return False


def terminate(pid):
    """End a process this tool started together with the ones it started; True when the system did it."""
    if os.name == "nt":
        # taskkill /T: npx starts node under cmd, so the whole tree has to go.
        command = ["taskkill", "/T", "/F", "/PID", str(pid)]
        try:
            return subprocess.run(command, capture_output=True, timeout=TASKKILL_SECONDS).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False
    if not own_group(pid):
        return False  # that group holds other programs now, so nothing in it is ours to end
    try:
        os.killpg(pid, signal.SIGTERM)  # the group the server got when it started, which is its own
    except OSError:
        return False
    return True


def set_option(command, flag, value):
    """The same command with that flag's value set: the value after the flag replaced, or the flag and value added."""
    arguments = list(command)
    if flag in arguments[:-1]:
        arguments[arguments.index(flag) + 1] = str(value)
    else:
        arguments += [flag, str(value)]
    return arguments


def with_port(command, port):
    """The same command on the port this run chose."""
    return set_option(command, "--port", port)


def board_command(command):
    """The board command with --non-interactive: its server has no window in which to ask anything."""
    if Path(command[0]).stem.casefold() != "backlog" or "browser" not in command[1:]:
        return list(command)
    if "--non-interactive" in command:
        return list(command)
    return [*command, "--non-interactive"]


def map_command(command, hmr):
    """The map command on this machine only, with the HMR port that was chosen for it."""
    return set_option(set_option(command, "--listen", "127.0.0.1"), "--hmr-port", hmr)


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


def wait_for_board(port, folder, deadline):
    """The folder the board at that port names last: asked until it names this project's, or the time runs out."""
    served = project_of(port)
    while not same_folder(served, folder) and time.monotonic() <= deadline:
        time.sleep(POLL_SECONDS)
        served = project_of(port)
    return served


def choose_ports(data, root, name, command, wanted):
    """(port, hmr port): the ports this server can run on. (0, None), with one line, when none is free."""
    port = port_for(data, root, name, wanted)
    if not port:
        print(f"The {PORTS_TRIED} ports from {wanted} up are all taken, so the {name} was not started. Free one.")
        return 0, None
    if name != "map":
        return port, None
    asked = value_after(command, "--hmr-port")
    hmr = hmr_for(data, root, asked)
    if not hmr:
        print(
            f"The {PORTS_TRIED} ports from {asked or HMR_FIRST} up are all taken, so the map's HMR port was not found."
        )
        return 0, None
    return port, hmr


def npx_download_check(name, command, download):
    """0 when the map may start; the exit code to end with, its lines already printed, when it may not.

    This runs before the lock is taken: the npx check may wait up to 120 seconds, and it needs only the entry's
    command, not the port. A map whose entry names npx would fetch its package on the first start, so the owner is
    asked first, unless --download says yes.
    """
    if name != "map" or download or Path(command[0]).stem.casefold() != "npx":
        return 0
    if shutil.which(command[0]) is None:
        return 0  # no npx on this machine: `build` prints how to install it
    # Whatever the entry names (pinned or not), npx would fetch it: the first argument that is not a flag.
    package = next((argument for argument in command[1:] if not argument.startswith("-")), "likec4")
    if downloaded(package):
        return 0
    print(f"The map is not downloaded yet: LikeC4 comes from npm, and this machine has no copy of {package}.")
    print("Nothing was started. After the owner says yes, run: python .pm/tools/pm_open.py map --download")
    return 2


def build(name, command, port, hmr, download):
    """(command, program, 0) for the server to start; (None, None, exit code) with the reason already printed."""
    command = with_port(command, port)
    command = board_command(command) if name == "board" else map_command(command, hmr)
    program = shutil.which(command[0])
    if program is None:
        print(
            f"The {name} needs `{command[0]}`, which this machine does not have: "
            f"{INSTALL.get(command[0], 'install it, then run this command again.')} Nothing was started."
        )
        return None, None, 1
    if name == "map" and Path(command[0]).stem.casefold() == "npx" and not download:
        # Without a yes the start itself must not download either: npx gets --no-install instead of -y.
        command = [
            command[0],
            "--no-install",
            *(argument for argument in command[1:] if argument not in ("-y", "--yes")),
        ]
    return command, program, 0


def wait_until_open(name, process, port, root, command, log_path):
    """Wait for the server to answer, and for the board to name this project; the exit code to end with."""
    address = ADDRESS.format(port=port)
    ran = " ".join(command)
    try:
        log = log_path.relative_to(root).as_posix()  # as the project sees it, so the line can be copied
    except ValueError:
        log = log_path.as_posix()
    deadline = time.monotonic() + WAIT_SECONDS
    while not answers(port):
        if process.poll() is not None:  # it stopped before it answered: waiting longer would not help
            print(f"The {name} stopped before it answered at {address} (exit code {process.returncode}).")
            print(f"I ran `{ran}`; its output is in {log}.")
            print("Read that file, then run this command again.")
            return 1
        if time.monotonic() > deadline:
            print(f"The {name} did not answer at {address} within {WAIT_SECONDS:g} seconds.")
            print(f"I ran `{ran}`; its output is in {log}.")
            print("Read that file, then run this command again.")
            return 1
        time.sleep(POLL_SECONDS)
    if process.poll() is not None:  # the port answers, but what this command started has quit: someone else answers
        print(f"Something answers at {address}, but the {name} I started stopped (exit code {process.returncode}).")
        print(f"Another program may hold port {port}; the {name}'s output is in {log}.")
        return 1
    served = wait_for_board(port, root, deadline) if name == "board" else None  # a port that answers proves nothing
    if name == "board" and not same_folder(served, root):
        print(f"Something answers at {address}, but it is not this project's board; it serves {served or 'nothing'}.")
        print(f"The board I started writes to {log}; read that file, then run this command again.")
        return 1
    show(address)
    print(f"The {name} is open at {address}")
    print(f"Command: {ran}")
    print(f"To stop it, run: python .pm/tools/pm_open.py stop {name}")
    return 0


def show(address):
    """Open the address in the browser, unless the caller shows it itself."""
    if BROWSER:
        webbrowser.open(address)


def open_server(name, download=False, root=None):
    """Open this project's board or map, starting it here when it is not this project's own server yet."""
    root = root or ROOT
    found = entry(root, name)
    if found is None:
        print(missing_entry_message(name))
        return 1
    command, wanted = found
    code = npx_download_check(name, command, download)  # up to 120 seconds: never while the lock is held
    if code:
        return code
    with locked() as held:
        if not held:
            return 1
        data = read_store()
        port, hmr = choose_ports(data, root, name, command, wanted)
        if not port:
            return 1
        recorded = server_of(data, root, name)
        state, served, address = ownership(root, name, recorded, port)
        if state != OURS and name == "map" and wanted != port:
            # The Claude preview and a terminal start the map on the entry's own port, while this project may have
            # recorded another one: a map serving this project's name there is opened instead of a second one.
            found = ownership(root, name, {}, wanted)
            if found[0] == OURS:
                port, (state, served, address) = wanted, found
        if state == OURS:
            print(f"The {name} is already running at {address}; I opened it in your browser.")
            show(address)
            keep(data, root, name, port)
            return 0
        if state == STOPPED and recorded.get("port") == port and process_of(recorded):
            # The lock is released before the wait, so a second run can arrive while ours is started but silent.
            print(f"The {name} is still starting at {address}; run this command again in a few seconds.")
            return 0
        if state == ANSWERS:
            who = f"another project ({served})" if served else "another program"
            print(f"Port {port} answers for {who}, so this project's {name} starts on a free port above.")
            if name == "map":
                why_not_recognised(root)
            free = choose_port(port, other_ports(data, root))
            if not free:
                print(f"The {PORTS_TRIED} ports from {port} up are all taken, so the {name} was not started.")
                return 1
            port, address = free, ADDRESS.format(port=free)
        made, program, code = build(name, command, port, hmr, download)
        if made is None:
            return code
        log_path = root / ".pm" / "local" / LOG.format(name=name)
        process = start([program, *made[1:]], root, log_path)
        if not save(data, root, name, port, pid=process.pid, started=start_time(process.pid), hmr=hmr):
            warn_store()
    return wait_until_open(name, process, port, root, made, log_path)  # the lock is not held while it starts


def why_not_recognised(root):
    """One line when this project's map name cannot tell a running map apart: no readable name, or a copied one."""
    own = map_name(root)
    if not own:
        print(
            "This project's map has no name I can read (plain JSON `name` in likec4.config.json), so a map already"
            " running cannot be recognised as this one; `pm_init.py --upgrade --map` writes one where none exists."
        )
    elif not made_here(root, own):
        print(
            f"The map name {own} was made for another folder (a copied or moved likec4.config.json), so a map serving"
            " it is not taken for this one; delete that file and run `pm_init.py --upgrade --map` to write this one's."
        )


def keep(data, root, name, port):
    """Remember a server that was already running on this port: its process id only while that process is ours."""
    server = server_of(data, root, name)
    pid = process_of(server) if server.get("port") == port else None
    started, hmr = (server.get("started"), server.get("hmr_port")) if pid else (None, None)
    if not save(data, root, name, port, pid=pid, started=started, hmr=hmr):
        warn_store()


def stop_server(name):
    """Stop the server this tool started for this project, and nothing else."""
    with locked() as held:
        if not held:
            return 1
        data = read_store()
        server = server_of(data, ROOT, name)
        if not server:
            print(f"No {name} is recorded for this project, so I stopped nothing.")
            return 0
        address = ADDRESS.format(port=server.get("port"))
        # The ownership check comes first (for a board it is a network answer), and the process is read once more
        # right before it is ended: an id read before that check may belong to another process by now.
        state = ownership(ROOT, name, server, server.get("port"))[0]
        if state == STOPPED:
            forget(data, ROOT, name)
            print(f"The {name} recorded for this project is not running, so I stopped nothing.")
            return 0
        pid = process_of(server)
        if not pid:
            forget(data, ROOT, name)
            print(f"The {name} at {address} was not started by this tool, so I left it running.")
            return 0
        if not terminate(pid):
            if os.name != "nt" and alive(pid) and not own_group(pid):
                print(f"The {name} (process id {pid}) is in another process group now, so I ended nothing.")
            else:
                print(
                    f"I could not stop the {name} (process id {pid}); it may already have stopped. "
                    "Nothing else was touched."
                )
            return 1
        # The port stays, so this project keeps its address; only the claim to a running process goes.
        record_of(data, ROOT)[name] = {key: value for key, value in server.items() if key not in ("pid", "started")}
        if not write_store(data):
            warn_store()
        print(f"Stopped the {name} (process id {pid}).")
        return 0


def window_address():
    return ADDRESS.format(port=WINDOW_PORT)


def window_running():
    """True when the project window answers on its port, and not some other program that holds it."""
    try:
        request = urllib.request.Request(window_address() + "/api/health")
        with urllib.request.urlopen(request, timeout=STATUS_TIMEOUT) as answer:
            return json.loads(answer.read().decode("utf-8")).get("name") == "pm-bridge"
    except (OSError, ValueError, AttributeError, http.client.HTTPException):
        return False


def open_window():
    """Put this project on the list, start the project window if it is not running, and open it."""
    with locked() as held:
        if not held:
            return 1
        data = read_store()
        record_of_project = record_of(data, ROOT)
        if not record_of_project:
            data.setdefault("projects", {})[folder_key(ROOT)] = {"name": ROOT.name}
            if not write_store(data):
                warn_store()
        if window_running():
            show(window_address())
            print(f"The project window is at {window_address()}")
            return 0
        if answers(WINDOW_PORT):
            print(f"Port {WINDOW_PORT} answers for another program, so the project window was not started.")
            return 1
        program = Path(__file__).resolve().parent / "pm_bridge.py"
        log_path = ROOT / ".pm" / "local" / LOG.format(name="window")
        process = start([sys.executable, str(program), "--port", str(WINDOW_PORT)], ROOT, log_path)
        data["window"] = {"port": WINDOW_PORT, "pid": process.pid, "started": start_time(process.pid)}
        if not write_store(data):
            warn_store()
    deadline = time.monotonic() + WAIT_SECONDS
    while not window_running():
        if process.poll() is not None or time.monotonic() > deadline:
            print(f"The project window did not answer at {window_address()}; its output is in {log_path}.")
            return 1
        time.sleep(POLL_SECONDS)
    show(window_address())
    print(f"The project window is at {window_address()}")
    print("To stop it, run: python .pm/tools/pm_open.py stop window")
    return 0


def stop_window():
    """End the project window this tool started, and nothing else."""
    with locked() as held:
        if not held:
            return 1
        data = read_store()
        server = data.get("window")
        pid = process_of(server) if isinstance(server, dict) else None
        if not pid:
            data.pop("window", None)
            if not write_store(data):
                warn_store()
            print("No project window started by this tool is running, so I stopped nothing.")
            return 0
        if not terminate(pid):
            print(f"I could not stop the project window (process id {pid}).")
            return 1
        data.pop("window", None)
        if not write_store(data):
            warn_store()
        print(f"Stopped the project window (process id {pid}). Everything else keeps running.")
        return 0


def show_list():
    """One line per registered project: its folder, then the address of its board and map and whether each is ours."""
    projects = read_store().get("projects", {})
    if not projects:
        print("No project is registered yet: `python .pm/tools/pm_open.py board` adds this one to the list.")
        return 0
    for key in sorted(projects):
        record = projects[key]
        name = record.get("name") or Path(key).name
        states = " · ".join(server_state(key, which, record.get(which)) for which in ("board", "map"))
        print(f"{name} ({key}) · {states}")
    return 0


def server_state(folder, name, server):
    """`board http://127.0.0.1:6421 running`, `map ... answers for another program`, or `map not started yet`."""
    server = server if isinstance(server, dict) else {}
    port = server.get("port")
    if not isinstance(port, int) or port <= 0:
        return f"{name} not started yet"
    state, _, address = ownership(folder, name, server, port)
    return f"{name} {address} {WORDS[state]}"


def set_opening(value):
    """Store the opening choice in the project list and say what it means."""
    with locked() as held:
        if not held:
            return 1
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
            "window: the project window for every project on this machine.\n"
            "stop board|map|window: stop what this tool started.\n"
            "list: every project opened this way, with its board and map and whether they run.\n"
            "opening ask|always|never: whether a session start offers the project window (the default is ask)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "name",
        choices=("board", "map", "window", "stop", "list", "opening"),
        metavar="board|map|window|stop|list|opening",
        help="what to do",
    )
    parser.add_argument("value", nargs="?", help="stop: board, map or window; opening: ask, always or never")
    parser.add_argument("--download", action="store_true", help="map only: let the first start download LikeC4")
    parser.add_argument("--root", help="another project's folder instead of this one")
    parser.add_argument("--no-browser", action="store_true", help="start or find the server, open no browser")
    args = parser.parse_args(argv)

    global ROOT, BROWSER
    BROWSER = not args.no_browser
    if args.root:
        ROOT = Path(args.root).resolve()
        if not (ROOT / ".pm").is_dir():
            print(f"{ROOT} has no .pm folder, so it is not a project.")
            return 1

    if args.name == "list":
        return show_list()
    if args.name == "stop":
        if args.value == "window":
            return stop_window()
        if args.value not in ("board", "map"):
            print("Say what to stop: `python .pm/tools/pm_open.py stop board`, `... stop map` or `... stop window`.")
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
    return open_window() if args.name == "window" else open_server(args.name, args.download)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            pass
    sys.exit(main())
