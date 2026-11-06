"""Serve the project window: one small local program for every project on this machine. Standard library only.

Usage: python .pm/tools/pm_bridge.py [--port 7420]

It listens on 127.0.0.1 only and stops with Ctrl+C. Closing it changes nothing: the files, the agents and the maps it
started keep working. The projects are the ones in pm_open's project list (`python .pm/tools/pm_open.py list`).

  GET  /               the page
  GET  /api/health     says this is the bridge, so a second start can tell it from another program
  GET  /api/projects   every registered project and the state of its map
  GET  /api/state?project=<id>   that project's own `pm_state.py` output; `state` is null with `why` when it fails
  POST /api/map/start  {"project": "<id>"}: pm_open starts the map, or finds the one already running
  POST /api/map/stop   {"project": "<id>"}: pm_open stops the map, only if pm_open started it

A map's `url` is given only after pm_open's ownership check says it is this project's own map: a port that
answers proves nothing.

What this program never does, under test in test_pm_bridge.py: write a file, touch .pm/backlog or .pm/decisions, call
a model, start an agent, or run anything but the two commands in map_command and state_command. A map entry in a
project's launch.json runs only when it is a LikeC4 start command (is_likec4); anything else in that file is refused.
A request with a foreign Host or Origin is refused, so a web page cannot reach it through a name of its own; a POST
must carry this page's Origin and a JSON body, so another site cannot start or stop anything.
"""

import argparse
import concurrent.futures
import http.client
import http.server
import json
import os
import re
import socketserver
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pm_open  # noqa: E402  (a sibling script, which keeps the project list and knows whose map a port serves)

NAME = "pm-bridge"
PORT = 7420
HOST = "127.0.0.1"  # the only address it listens on; there is deliberately no option for another
PAGE = HERE / "pm_bridge.html"
STATE_VERSION = 2  # the pm_state output this program can read; an older project is told to upgrade
STATE_SECONDS = 20
START_SECONDS = 160  # pm_open may check the npx cache (up to 120 s), then waits for the map to answer
STOP_SECONDS = 20
HEALTH_SECONDS = 2
BODY_LIMIT = 4096
NO_WINDOW = 0x08000000 if os.name == "nt" else 0  # no console flashes up on Windows
# The page is one file with its style and script inside; a frame may only ever show a map on this machine (the API
# gives no other address), and no other page may frame this one.
PAGE_POLICY = (
    "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "frame-src http:; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
)


def is_likec4(command):
    """True for `npx [-y] likec4[@version] start|dev ...` or `likec4 start|dev ...`: all a map entry may run from here."""
    program, *words = command
    stem = Path(program).stem.lower()
    if stem == "npx":
        while words and words[0] in ("-y", "--yes"):
            words = words[1:]
    elif stem == "likec4":
        words = ["likec4", *words]
    else:
        return False
    return len(words) > 1 and bool(re.fullmatch(r"likec4(@[\w.-]+)?", words[0])) and words[1] in ("start", "dev")


def map_command(folder, action):
    """The one way to start or stop a project's map: this program's own pm_open, pointed at that folder."""
    tool = str(HERE / "pm_open.py")
    words = ["map"] if action == "start" else ["stop", "map"]
    return [sys.executable, tool, *words, "--root", folder, "--no-browser"]


def state_command(folder):
    """The one way to read a project's state: that project's own pm_state, which writes nothing."""
    return [sys.executable, str(Path(folder) / ".pm" / "tools" / "pm_state.py")]


def run(command, folder, seconds):
    """(exit code, stdout, stderr) of a command from map_command or state_command; the code is None if it did not end."""
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    try:
        done = subprocess.run(
            command,
            cwd=folder,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=seconds,
            creationflags=NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return None, "", f"no answer within {seconds} seconds"
    except OSError as error:
        return None, "", str(error)
    return done.returncode, done.stdout, done.stderr


def project_folder(project_id):
    """The folder of the registered project with this id, or None: only the project list names what may be run."""
    for key in pm_open.read_store().get("projects", {}):
        if pm_open.path_code(key) == project_id and Path(key).is_dir():
            return key
    return None


def map_state(folder, server):
    """{"state": ...}: `none` without a map layer, `running` with its `url`, `foreign` or `stopped` without one."""
    found = pm_open.entry(Path(folder), "map")
    if found is None:
        return {"state": "none"}
    server = server if isinstance(server, dict) else {}
    state = pm_open.STOPPED
    # The recorded port first; a map the Claude preview or a terminal started sits on the entry's own port.
    for port in dict.fromkeys((server.get("port"), found[1])):
        # The record's process proves its own port only; the address is the loopback the check found the map on.
        seen, _, address = pm_open.ownership(folder, "map", server if port == server.get("port") else {}, port)
        if seen == pm_open.OURS:
            return {"state": "running", "url": address + "/"}
        if seen == pm_open.ANSWERS:
            state = seen
    return {"state": "foreign" if state == pm_open.ANSWERS else "stopped"}


def project(item):
    """One registered project with its id, name, folder and map; a folder that is gone says so."""
    key, record = item
    here = Path(key).is_dir()
    return {
        "id": pm_open.path_code(key),
        "name": record.get("name") or Path(key).name,
        "folder": key,
        "found": here,
        "map": map_state(key, record.get("map")) if here else {"state": "none"},
    }


def projects():
    """Every registered project; asked side by side, since each map check waits on its ports."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(project, sorted(pm_open.read_store().get("projects", {}).items())))


def project_state(folder):
    """{"state": <pm_state output>} or {"state": None, "why": ...}; a source that fails is said, never guessed."""
    tool = state_command(folder)[-1]
    if not Path(tool).is_file():
        return {"state": None, "why": "this project's .pm has no pm_state.py yet; upgrade it"}
    code, out, err = run(state_command(folder), folder, STATE_SECONDS)
    if code != 0:
        return {"state": None, "why": (err or out).strip()[-300:] or f"pm_state ended with code {code}"}
    try:
        state = json.loads(out)
    except ValueError:
        return {"state": None, "why": "pm_state did not print JSON"}
    if not isinstance(state, dict) or state.get("version") != STATE_VERSION:
        return {
            "state": None,
            "why": f"pm_state prints a shape this bridge does not read (it reads {STATE_VERSION}); upgrade this project",
        }
    return {"state": state}


def change_map(folder, action):
    """Start or stop a map through pm_open; its own words come back, and the map's state after it."""
    record = pm_open.record_of(pm_open.read_store(), folder)
    found = pm_open.entry(Path(folder), "map")
    if action == "start" and (found is None or not is_likec4(found[0])):
        why = "This project's map entry in .claude/launch.json is not a LikeC4 start command, so nothing was started."
        return {"ok": False, "message": why, "map": map_state(folder, record.get("map"))}
    seconds = START_SECONDS if action == "start" else STOP_SECONDS
    code, out, err = run(map_command(folder, action), folder, seconds)
    record = pm_open.record_of(pm_open.read_store(), folder)
    return {"ok": code == 0, "message": (out + err).strip()[-600:], "map": map_state(folder, record.get("map"))}


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = NAME
    sys_version = ""

    def log_message(self, format, *args):
        """Quiet: this program has no log of its own."""

    def send(self, status, body, kind, policy=None):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if policy:
            self.send_header("Content-Security-Policy", policy)
        self.end_headers()
        self.wfile.write(body)

    def reply(self, status, data):
        self.send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def refuse(self, status, why):
        self.reply(status, {"error": why})

    def our_host(self):
        return self.headers.get("Host", "").lower() in (
            f"127.0.0.1:{self.server.port}",
            f"localhost:{self.server.port}",
        )

    def our_origin(self):
        return self.headers.get("Origin", "").lower() in (
            f"http://127.0.0.1:{self.server.port}",
            f"http://localhost:{self.server.port}",
        )

    def do_GET(self):
        if not self.our_host() or ("Origin" in self.headers and not self.our_origin()):
            return self.refuse(403, "foreign Host or Origin")
        url = urlsplit(self.path)
        if url.path == "/":
            return self.send(200, PAGE.read_bytes(), "text/html; charset=utf-8", PAGE_POLICY)
        if url.path == "/api/health":
            return self.reply(200, {"name": NAME, "folder": str(pm_open.ROOT)})
        if url.path == "/api/projects":
            return self.reply(200, {"projects": projects()})
        if url.path == "/api/state":
            folder = project_folder(parse_qs(url.query).get("project", [""])[0])
            if folder is None:
                return self.refuse(404, "no such project")
            return self.reply(200, project_state(folder))
        return self.refuse(404, "no such address")

    def body(self):
        """The JSON object sent with a POST, or None when it is too long or is not one."""
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return None
        if not 0 < length <= BODY_LIMIT:
            return None
        try:
            data = json.loads(self.rfile.read(length))
        except ValueError:
            return None
        return data if isinstance(data, dict) else None

    def do_POST(self):
        if not self.our_host() or not self.our_origin():
            return self.refuse(403, "foreign Host or Origin")
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            return self.refuse(415, "send JSON")
        actions = {"/api/map/start": "start", "/api/map/stop": "stop"}
        action = actions.get(urlsplit(self.path).path)
        if action is None:
            return self.refuse(404, "no such address")
        data = self.body()
        folder = project_folder(data.get("project")) if data else None
        if folder is None:
            return self.refuse(404, "no such project")
        return self.reply(200, change_map(folder, action))


class Bridge(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False  # one bridge per machine: a second one must fail to bind, on Windows too

    def __init__(self, port):
        super().__init__((HOST, port), Handler)
        self.port = self.server_address[1]

    def server_bind(self):
        """As HTTPServer does, without its name lookup: that takes seconds on Windows and nothing here reads it."""
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = HOST, self.server_address[1]


def is_bridge(port):
    """True when the program on that port says it is the bridge."""
    connection = http.client.HTTPConnection(HOST, port, timeout=HEALTH_SECONDS)
    try:
        connection.request("GET", "/api/health", headers={"Host": f"{HOST}:{port}"})
        return json.loads(connection.getresponse().read()).get("name") == NAME
    except (OSError, ValueError, http.client.HTTPException, AttributeError):
        return False
    finally:
        connection.close()


def main(argv=None):
    parser = argparse.ArgumentParser(prog="pm_bridge.py", description="Serve the project window on 127.0.0.1.")
    parser.add_argument("--port", type=int, default=PORT, help=f"the port to listen on (default {PORT})")
    args = parser.parse_args(argv)
    try:
        server = Bridge(args.port)
    except OSError:
        if is_bridge(args.port):
            print(f"The project window already runs at http://{HOST}:{args.port}")
            return 0
        print(f"Port {args.port} is taken by another program; choose another with --port.")
        return 1
    print(f"The project window is at http://{HOST}:{server.port}  (Ctrl+C stops it; everything else keeps running)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
