from __future__ import annotations

import json
import math
import os
import signal
import socket
import subprocess
import sys
import threading
import uuid
import webbrowser
from collections import OrderedDict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from urllib.parse import urlsplit

from .config import load_config
from .freshness import build_status_report

COMMANDS = {
    "build-index", "sync", "status", "bfetch", "bindex", "bsearch",
    "optimize-db", "match", "tsearch", "combo", "analyze", "selfcheck",
}
JSON_COMMANDS = COMMANDS - {"build-index", "sync"}
ASSETS = {"/": ("index.html", "text/html"), "/app.css": ("app.css", "text/css"), "/app.js": ("app.js", "text/javascript")}
LOOPBACKS = {"127.0.0.1", "localhost", "::1"}
MAX_BODY = 64 * 1024
MAX_OUTPUT = 4 * 1024 * 1024


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _hostname(value: str) -> str | None:
    try:
        return urlsplit(f"//{value}").hostname
    except ValueError:
        return None


def _json_safe(value):
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value) if abs(value) > 2**53 - 1 else value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return str(value)


class JobManager:
    def __init__(self, max_history: int = 12):
        self.max_history = max_history
        self.jobs: OrderedDict[str, dict] = OrderedDict()
        self.active_id: str | None = None
        self.workers: dict[str, threading.Thread] = {}
        self.closing = False
        self.lock = threading.Lock()

    def _snapshot(self, job: dict) -> dict:
        return {key: value for key, value in job.items() if key not in {"process", "cancel_requested"}}

    def _summary(self, job: dict) -> dict:
        return {
            key: value
            for key, value in self._snapshot(job).items()
            if key not in {"effective_args", "output", "output_type", "stderr"}
        }

    def _prune(self) -> None:
        for job_id in list(self.jobs):
            if len(self.jobs) <= self.max_history:
                break
            if job_id != self.active_id and self.jobs[job_id]["status"] != "running":
                del self.jobs[job_id]

    def start(self, command: str, args: list[str]) -> dict:
        if command not in COMMANDS:
            raise ValueError(f"unsupported command: {command}")
        if not isinstance(args, list) or not all(isinstance(arg, str) and "\0" not in arg for arg in args):
            raise ValueError("args must be an array of strings")
        effective_args = list(args)
        if command in JSON_COMMANDS and "--json" not in effective_args:
            separator = effective_args.index("--") if "--" in effective_args else len(effective_args)
            effective_args.insert(separator, "--json")
        with self.lock:
            if self.closing:
                raise RuntimeError("server is shutting down")
            if self.active_id is not None:
                raise RuntimeError("another job is already running")
            job_id = uuid.uuid4().hex
            job = {
                "id": job_id,
                "command": command,
                "args": list(args),
                "effective_args": effective_args,
                "status": "running",
                "created_at": _now(),
                "started_at": None,
                "finished_at": None,
                "returncode": None,
                "output": None,
                "output_type": None,
                "output_truncated": False,
                "stderr": "",
                "process": None,
                "cancel_requested": False,
            }
            self.jobs[job_id] = job
            self.active_id = job_id
            self._prune()
            worker = threading.Thread(target=self._run, args=(job_id,), daemon=True)
            self.workers[job_id] = worker
            worker.start()
        return self.get(job_id)

    def _run(self, job_id: str) -> None:
        with self.lock:
            job = self.jobs[job_id]
            argv = [sys.executable, "-m", "oeis_matcher.cli", job["command"], *job["effective_args"]]
            job["started_at"] = _now()
        try:
            with self.lock:
                if job["cancel_requested"] or self.closing:
                    job.update(status="cancelled", finished_at=_now(), returncode=-signal.SIGTERM)
                    return
            process = subprocess.Popen(
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                start_new_session=os.name != "nt",
            )
            with self.lock:
                job["process"] = process
                cancelled = job["cancel_requested"]
            if cancelled:
                self._stop(process)
            stdout, stderr, truncated = self._capture(process)
            returncode = process.returncode
            try:
                output = json.loads(stdout) if stdout.strip() else None
                output_type = "json" if stdout.strip() else None
            except json.JSONDecodeError:
                output, output_type = stdout, "text"
            with self.lock:
                job.update(
                    status="cancelled" if job["cancel_requested"] else ("completed" if returncode == 0 else "failed"),
                    finished_at=job["finished_at"] or _now(),
                    returncode=returncode,
                    output=output,
                    output_type=output_type,
                    stderr=stderr,
                    output_truncated=truncated,
                    process=None,
                )
        except Exception as exc:
            with self.lock:
                job.update(status="cancelled" if job["cancel_requested"] else "failed", finished_at=_now(), stderr=str(exc), process=None)
        finally:
            with self.lock:
                if self.active_id == job_id:
                    self.active_id = None
                self.workers.pop(job_id, None)
                self._prune()

    @staticmethod
    def _capture(process: subprocess.Popen) -> tuple[str, str, bool]:
        captured: dict[str, str] = {}
        truncated = [False]

        def read(name: str, stream) -> None:
            parts, remaining = [], MAX_OUTPUT
            while chunk := stream.read(64 * 1024):
                kept = min(len(chunk), remaining)
                if kept:
                    parts.append(chunk[:kept])
                    remaining -= kept
                if kept < len(chunk):
                    truncated[0] = True
            captured[name] = "".join(parts)

        readers = [
            threading.Thread(target=read, args=("stdout", process.stdout), daemon=True),
            threading.Thread(target=read, args=("stderr", process.stderr), daemon=True),
        ]
        for reader in readers:
            reader.start()
        process.wait()
        for reader in readers:
            reader.join()
        return captured.get("stdout", ""), captured.get("stderr", ""), truncated[0]

    @staticmethod
    def _stop(process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return
        try:
            if os.name != "nt":
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
            process.wait(timeout=1)
        except (OSError, subprocess.TimeoutExpired):
            if process.poll() is None:
                try:
                    if os.name != "nt":
                        os.killpg(process.pid, signal.SIGKILL)
                    else:
                        process.kill()
                except OSError:
                    pass
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass

    def get(self, job_id: str) -> dict:
        with self.lock:
            if job_id not in self.jobs:
                raise KeyError(job_id)
            return self._snapshot(self.jobs[job_id])

    def list(self) -> dict:
        with self.lock:
            return {"active_job_id": self.active_id, "jobs": [self._summary(job) for job in reversed(self.jobs.values())]}

    def cancel(self, job_id: str) -> dict:
        with self.lock:
            if job_id not in self.jobs:
                raise KeyError(job_id)
            job = self.jobs[job_id]
            if job["status"] != "running":
                return self._snapshot(job)
            job["cancel_requested"] = True
            process = job["process"]
            worker = self.workers.get(job_id)
        if process is not None:
            self._stop(process)
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=2)
        with self.lock:
            return self._snapshot(job)

    def close(self) -> None:
        with self.lock:
            self.closing = True
            active_id = self.active_id
            workers = list(self.workers.values())
        if active_id is not None:
            self.cancel(active_id)
        for worker in workers:
            worker.join(timeout=3)


def _status() -> dict:
    config = load_config()
    paths, freshness = config["paths"], config["freshness"]
    return build_status_report(
        stripped_path=Path(paths["stripped"]),
        names_path=Path(paths["names"]),
        keywords_path=Path(paths["keywords"]),
        db_path=Path(paths["db"]),
        metadata_path=Path(freshness["metadata_path"]),
        max_age_days=float(freshness["max_age_days"]),
    )


def make_handler(manager: JobManager):
    class Handler(BaseHTTPRequestHandler):
        server_version = "oeis-ui/1"

        def _allowed(self) -> bool:
            host = self.headers.get("Host", "")
            if _hostname(host) not in LOOPBACKS:
                return False
            origin = self.headers.get("Origin")
            if not origin:
                return True
            parsed = urlsplit(origin)
            return parsed.scheme == "http" and parsed.netloc.lower() == host.lower()

        def _json(self, code: int, payload) -> None:
            body = json.dumps(_json_safe(payload), separators=(",", ":"), allow_nan=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _asset(self, name: str, content_type: str) -> None:
            try:
                body = resources.files("oeis_matcher").joinpath("web_assets", name).read_bytes()
            except (FileNotFoundError, ModuleNotFoundError):
                return self._json(404, {"error": "asset not found"})
            self.send_response(200)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

        def _job_id(self) -> str | None:
            parts = urlsplit(self.path).path.strip("/").split("/")
            return parts[2] if len(parts) == 3 and parts[:2] == ["api", "jobs"] else None

        def do_GET(self) -> None:
            if not self._allowed():
                return self._json(403, {"error": "loopback Host and Origin required"})
            path = urlsplit(self.path).path
            if path in ASSETS:
                return self._asset(*ASSETS[path])
            if path == "/api/status":
                return self._json(200, _status())
            if path == "/api/jobs":
                return self._json(200, manager.list())
            job_id = self._job_id()
            if job_id:
                try:
                    return self._json(200, manager.get(job_id))
                except KeyError:
                    return self._json(404, {"error": "job not found"})
            return self._json(404, {"error": "not found"})

        def do_POST(self) -> None:
            if not self._allowed():
                return self._json(403, {"error": "loopback Host and Origin required"})
            if urlsplit(self.path).path != "/api/jobs":
                return self._json(404, {"error": "not found"})
            if self.headers.get_content_type() != "application/json":
                return self._json(415, {"error": "application/json required"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return self._json(400, {"error": "invalid Content-Length"})
            if length <= 0 or length > MAX_BODY:
                return self._json(413, {"error": "request body must be 1..65536 bytes"})
            try:
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict) or not isinstance(payload.get("command"), str):
                    raise ValueError("body must contain command and args")
                job = manager.start(payload["command"], payload.get("args", []))
                return self._json(202, job)
            except json.JSONDecodeError:
                return self._json(400, {"error": "invalid JSON"})
            except ValueError as exc:
                return self._json(400, {"error": str(exc)})
            except RuntimeError as exc:
                return self._json(409, {"error": str(exc)})

        def do_DELETE(self) -> None:
            if not self._allowed():
                return self._json(403, {"error": "loopback Host and Origin required"})
            job_id = self._job_id()
            if not job_id:
                return self._json(404, {"error": "not found"})
            try:
                return self._json(200, manager.cancel(job_id))
            except KeyError:
                return self._json(404, {"error": "job not found"})

        def log_message(self, fmt: str, *args) -> None:
            pass

    return Handler


def make_server(host: str = "127.0.0.1", port: int = 8766, *, manager: JobManager | None = None) -> ThreadingHTTPServer:
    if host not in LOOPBACKS:
        raise ValueError("host must be a loopback address")
    class Server(ThreadingHTTPServer):
        address_family = socket.AF_INET6 if ":" in host else socket.AF_INET
        daemon_threads = True

    return Server((host, port), make_handler(manager or JobManager()))


def _open_browser(url: str) -> None:
    def open_url() -> None:
        try:
            if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
                subprocess.Popen(
                    ["cmd.exe", "/c", "start", "", url],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=open_url, daemon=True).start()


def serve(host: str = "127.0.0.1", port: int = 8766, open_browser: bool = True) -> None:
    manager = JobManager()
    server = make_server(host, port, manager=manager)
    shown_host = f"[{host}]" if ":" in host else host
    url = f"http://{shown_host}:{server.server_port}/"
    print(f"OEIS UI: {url}")
    if open_browser:
        _open_browser(url)

    previous_handlers = {}
    if threading.current_thread() is threading.main_thread():
        def stop_server(_signum, _frame) -> None:
            raise KeyboardInterrupt

        for sig in (signal.SIGTERM, getattr(signal, "SIGHUP", None)):
            if sig is not None:
                previous_handlers[sig] = signal.signal(sig, stop_server)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)
        manager.close()
        server.server_close()
