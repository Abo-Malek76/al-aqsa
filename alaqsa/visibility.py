"""Is the app's window actually on screen? (Hyprland)

The app counts as visible when its window's workspace is showing on any monitor —
focused or not, so it keeps animating on a second monitor — and no fullscreen
window covers it. It's hidden when it's on a workspace nobody is looking at, or
behind a fullscreen game.

Listens to Hyprland's event socket instead of polling, so it costs nothing while
nothing changes. Outside Hyprland it always reports visible.
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from pathlib import Path

# Events after which visibility may have changed
EVENTS = (
    "workspace", "workspacev2", "focusedmon", "focusedmonv2", "activewindow", "activewindowv2",
    "fullscreen", "movewindow", "movewindowv2", "openwindow", "closewindow", "activespecial",
    "activespecialv2", "moveworkspace", "moveworkspacev2", "monitoradded", "monitorremoved",
    "changefloatingmode", "minimized",
)


def _socket_dir() -> Path | None:
    signature = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    if not signature:
        return None
    for runtime in (os.environ.get("XDG_RUNTIME_DIR"), f"/run/user/{os.getuid()}"):
        if runtime and (Path(runtime) / "hypr" / signature / ".socket.sock").exists():
            return Path(runtime) / "hypr" / signature
    return None


def _request(directory: Path, command: str):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(2)
        sock.connect(str(directory / ".socket.sock"))
        sock.sendall(command.encode())
        chunks = []
        while chunk := sock.recv(65536):
            chunks.append(chunk)
    return json.loads(b"".join(chunks))


def _ancestors() -> list[int]:
    """Our process and its parents, nearest first (our terminal window's process is one of them)."""
    pids, pid = [], os.getpid()
    while pid > 1 and pid not in pids:
        pids.append(pid)
        try:
            pid = int(Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            break
    return pids


class VisibilityWatcher:
    def __init__(self, on_change) -> None:
        self.on_change = on_change  # called with True/False from a background thread
        self.directory = _socket_dir()
        self.visible = True
        self._ancestors = _ancestors()
        self._address: str | None = None

    @property
    def supported(self) -> bool:
        return self.directory is not None

    def start(self) -> None:
        if debug_log := os.environ.get("AL_AQSA_DEBUG_LOG"):
            with open(debug_log, "a") as file:
                file.write(f"{time.time():.1f} watcher start, supported={self.supported}\n")
        if self.supported:
            threading.Thread(target=self._listen, daemon=True).start()

    def check(self) -> bool:
        """Work out visibility now (falls back to visible if anything's unclear)."""
        try:
            clients = _request(self.directory, "j/clients")
            monitors = _request(self.directory, "j/monitors")
            workspaces = {w["id"]: w for w in _request(self.directory, "j/workspaces")}
        except (OSError, ValueError):
            return True
        # Our window belongs to the nearest ancestor that has one (further up could be
        # e.g. the terminal we were started from)
        mine = []
        for pid in self._ancestors:
            mine = [c for c in clients if c.get("pid") == pid]
            if mine:
                break
        if len(mine) > 1:  # a terminal sharing one process across windows: prefer ours by class
            mine = [c for c in mine if "al-aqsa" in c.get("class", "")] or mine
        if not mine:
            return True
        window = mine[0]
        self._address = window.get("address")
        if window.get("hidden"):  # e.g. a background tab in a window group
            return False
        workspace = window.get("workspace", {}).get("id")
        shown = set()
        for monitor in monitors:
            shown.add(monitor.get("activeWorkspace", {}).get("id"))
            special = monitor.get("specialWorkspace", {}).get("id")
            if special:
                shown.add(special)
        if workspace not in shown:
            return False
        info = workspaces.get(workspace, {})
        covered = info.get("hasfullscreen") and not window.get("fullscreen") and info.get("lastwindow") != self._address
        return not covered

    def _update(self) -> None:
        visible = self.check()
        if debug_log := os.environ.get("AL_AQSA_DEBUG_LOG"):
            with open(debug_log, "a") as file:
                file.write(f"{time.time():.1f} check={visible} window={self._address}\n")
        if visible != self.visible:
            self.visible = visible
            self.on_change(visible)

    def _listen(self) -> None:
        self._update()
        while True:
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                    sock.connect(str(self.directory / ".socket2.sock"))
                    buffer = b""
                    while True:
                        data = sock.recv(4096)
                        if not data:
                            break
                        buffer += data
                        *lines, buffer = buffer.split(b"\n")
                        if any(line.split(b">>", 1)[0].decode(errors="ignore") in EVENTS for line in lines):
                            time.sleep(0.05)  # let Hyprland settle (events come in bursts)
                            self._update()
            except OSError:
                pass
            time.sleep(2)  # Hyprland restarted or the socket hiccuped: reconnect
