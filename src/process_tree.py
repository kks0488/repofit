"""Run a judge in its own session and clean up only its identified descendants."""

import ctypes
import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

MARKER = "REPOFIT_JUDGE_ID"
ProcessInfo = tuple[int, int, int | str, str]


def process_table() -> dict[int, ProcessInfo]:
    """PID -> (parent PID, group, start identity, state), using procfs or ps."""
    table = {}
    if sys.platform != "linux":
        result = subprocess.run(["ps", "-axo", "pid=,ppid=,pgid=,lstart=,stat="],
                                capture_output=True, text=True, check=True, timeout=10)
        for line in result.stdout.splitlines():
            fields = line.split()
            if len(fields) >= 9:
                table[int(fields[0])] = (int(fields[1]), int(fields[2]),
                                         " ".join(fields[3:8]), fields[8][0])
        return table
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            table[int(entry.name)] = (int(fields[1]), int(fields[2]), int(fields[19]), fields[0])
        except (OSError, ValueError, IndexError):
            continue  # Exited during the snapshot, or not readable by this user.
    return table


class JudgeProcesses:
    def __init__(self, *, adopt_orphans: bool = False):
        self.adopt_orphans = adopt_orphans
        self.owner = os.getpid()
        self.marker = uuid.uuid4().hex
        self.known: dict[int, int | str] = {}
        # Adopt orphaned grandchildren so cleanup can reap them instead of leaving
        # zombies to a container's PID 1. Never wait for an unrelated child.
        if adopt_orphans and sys.platform == "linux" and ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), "Cannot track orphaned judge children")

    def scan(self) -> dict[int, ProcessInfo]:
        table = process_table()
        marker = f"{MARKER}={self.marker}".encode()
        marked = set()
        if sys.platform != "linux":
            result = subprocess.run(["ps", "eww", "-axo", "pid=,command="],
                                    capture_output=True, text=True, check=True, timeout=10)
            for line in result.stdout.splitlines():
                fields = line.split()
                if fields and marker.decode() in fields[1:]:
                    marked.add(int(fields[0]))
        for pid, (parent, _, started, _) in table.items():
            if self.adopt_orphans and sys.platform == "linux" and parent == self.owner:
                self.known[pid] = started
            if self.known.get(pid) == started or (self.adopt_orphans and sys.platform == "linux"):
                continue
            try:
                # The unique inherited marker also finds a child that detached and
                # lost its parent between snapshots. It is never a name match.
                if (pid in marked or (sys.platform == "linux"
                        and marker in Path(f"/proc/{pid}/environ").read_bytes().split(b"\0"))):
                    self.known[pid] = started
            except OSError:
                pass
        while True:
            children = {pid: started for pid, (parent, _, started, _) in table.items()
                        if parent in self.known and table.get(parent, (0, 0, -1, ""))[2] == self.known[parent]
                        and pid not in self.known}
            if not children:
                break
            self.known.update(children)
        return {pid: info for pid, info in table.items() if self.known.get(pid) == info[2]}

    def signal(self, sig: int, root: int) -> bool:
        owned = self.scan()
        # Only this invocation can create members of its fresh session's root
        # group. Verify a known member is still there before addressing the group.
        if any(group == root and state != "Z" for _, group, _, state in owned.values()):
            try:
                os.killpg(root, sig)
            except ProcessLookupError:
                pass
        for pid, (_, _, started, state) in owned.items():
            if state == "Z":
                continue
            # Check start time again immediately before signalling: PID reuse
            # must never target another invocation or a pre-existing process.
            current = process_table().get(pid)
            if current is not None and current[2] == started:
                try:
                    os.kill(pid, sig)
                except ProcessLookupError:
                    pass
        return any(info[3] != "Z" for info in owned.values())

    def cleanup(self, process: subprocess.Popen) -> None:
        deadline = time.monotonic() + 5
        self.signal(signal.SIGTERM, process.pid)
        while True:
            process.poll()
            owned = self.scan()
            for pid, (_, _, _, state) in owned.items():
                if pid != process.pid and state == "Z":
                    try:
                        os.waitpid(pid, os.WNOHANG)
                    except ChildProcessError:
                        pass
            if not self.scan():
                break
            if time.monotonic() >= deadline:
                self.signal(signal.SIGKILL, process.pid)
                break
            time.sleep(0.05)
        process.wait()
        # SIGKILL is asynchronous. Reap only recorded children after they exit.
        deadline = time.monotonic() + 5
        while self.scan():
            self.signal(signal.SIGKILL, process.pid)
            for pid in self.known:
                if pid != process.pid:
                    try:
                        os.waitpid(pid, os.WNOHANG)
                    except ChildProcessError:
                        pass
            if not self.scan():
                break
            if time.monotonic() >= deadline:
                raise OSError("Judge descendants did not exit after SIGKILL")
            time.sleep(0.05)


def _run_judge(command: list[str], *, cwd: Path, env: dict[str, str], timeout: float,
              cancel: threading.Event | None = None) -> subprocess.CompletedProcess:
    tracker = JudgeProcesses(adopt_orphans=True)
    if cancel is not None and cancel.is_set():
        raise InterruptedError("Preview interrupted")
    process = subprocess.Popen(command, cwd=cwd, env={**env, MARKER: tracker.marker},
                               start_new_session=True, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + timeout
        while True:
            tracker.scan()
            if cancel is not None and cancel.is_set():
                raise InterruptedError("Preview interrupted")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout)
            try:
                stdout, stderr = process.communicate(timeout=min(0.1, remaining))
                return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
            except subprocess.TimeoutExpired:
                pass
    finally:
        try:
            tracker.cleanup(process)
        finally:
            process.stdout.close()
            process.stderr.close()


def run_judge(command: list[str], *, cwd: Path, env: dict[str, str], timeout: float,
              cancel: threading.Event | None = None) -> subprocess.CompletedProcess:
    """Use a dedicated supervisor so reparented children have one clear owner."""
    if cancel is not None and cancel.is_set():
        raise InterruptedError("Preview interrupted")
    supervisor = None
    interrupted = False
    try:
        # Preserve cancellation even if it arrives before the new interpreter has
        # installed its handlers. The supervisor unblocks these after setup.
        previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGINT})
        try:
            supervisor = subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), str(timeout), *command],
                cwd=cwd, env=env, start_new_session=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
        while True:
            if cancel is not None and cancel.is_set() and not interrupted:
                supervisor.send_signal(signal.SIGTERM)
                interrupted = True
            try:
                stdout, _ = supervisor.communicate(timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                pass
        if interrupted:
            raise InterruptedError("Preview interrupted")
        if supervisor.returncode != 0:
            raise OSError("Judge supervisor failed")
        result = json.loads(stdout)
        if result.get("timeout"):
            raise subprocess.TimeoutExpired(command, timeout)
        if result.get("error"):
            raise OSError("Judge failed or descendants could not be cleaned up")
        return subprocess.CompletedProcess(command, result["returncode"], result["stdout"], result["stderr"])
    finally:
        if supervisor is not None and supervisor.poll() is None:
            # A direct call may receive KeyboardInterrupt instead of an Event.
            # The supervisor handles TERM and finishes all child cleanup first.
            supervisor.send_signal(signal.SIGTERM)
            supervisor.communicate()
        if supervisor is not None:
            supervisor.stdout.close()
            supervisor.stderr.close()


if __name__ == "__main__":
    stopping = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    signal.signal(signal.SIGINT, lambda *_: stopping.set())
    signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGTERM, signal.SIGINT})
    try:
        completed = _run_judge(sys.argv[2:], cwd=Path.cwd(), env=dict(os.environ),
                               timeout=float(sys.argv[1]), cancel=stopping)
        payload = {"returncode": completed.returncode, "stdout": completed.stdout,
                   "stderr": completed.stderr}
    except subprocess.TimeoutExpired:
        payload = {"timeout": True}
    except Exception:
        payload = {"error": True}
    print(json.dumps(payload), flush=True)
