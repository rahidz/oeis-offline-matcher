from __future__ import annotations

import json
import signal
import sys
import threading
import time
import tomllib
from html.parser import HTMLParser
from http.client import HTTPMessage
from importlib import resources
from io import BytesIO, StringIO
from pathlib import Path

import pytest

from oeis_matcher import web


class _UIParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.commands, self.assets, self.profiles = set(), set(), set()
        self.expert_labels = 0
        self.expert_controls = 0
        self.expert_help: list[str] = []
        self._in_analyze_expert_controls = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "details" and values.get("id") == "analyze-expert-controls":
            self._in_analyze_expert_controls = True
        elif tag == "label" and self._in_analyze_expert_controls:
            self.expert_labels += 1
            if values.get("data-help", "").strip():
                self.expert_help.append(values["data-help"])
        if tag in {"input", "select", "textarea"} and self._in_analyze_expert_controls:
            self.expert_controls += 1
        if tag == "form" and values.get("data-command"):
            self.commands.add(values["data-command"])
        if tag in {"link", "script"}:
            self.assets.add(values.get("href") or values.get("src"))
        if tag == "input" and values.get("name") == "preset":
            self.profiles.add(values.get("value"))

    def handle_endtag(self, tag):
        if tag == "details" and self._in_analyze_expert_controls:
            self._in_analyze_expert_controls = False


def _request(handler, method, path, body=b"", content_type=None, extra_headers=None):
    if not isinstance(body, bytes):
        body = json.dumps(body).encode()
    request = handler.__new__(handler)
    request.path = path
    request.request_version = "HTTP/1.1"
    request.requestline = f"{method} {path} HTTP/1.1"
    request.client_address = ("127.0.0.1", 1234)
    request.headers = HTTPMessage()
    request.headers["Host"] = "127.0.0.1"
    request.headers["Content-Length"] = str(len(body))
    if content_type:
        request.headers["Content-Type"] = content_type
    for key, value in (extra_headers or {}).items():
        if key in request.headers:
            request.headers.replace_header(key, value)
        else:
            request.headers[key] = value
    request.rfile, request.wfile = BytesIO(body), BytesIO()
    request.log_message = lambda *_: None
    getattr(request, f"do_{method}")()
    head, payload = request.wfile.getvalue().split(b"\r\n\r\n", 1)
    lines = head.decode("latin-1").splitlines()
    headers = {key.lower(): value.strip() for key, value in (line.split(":", 1) for line in lines[1:])}
    return int(lines[0].split()[1]), headers, payload


def _wait_for(manager, job_id, status, timeout=2, settled=False):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = manager.get(job_id)
        if job["status"] == status and (not settled or job["returncode"] is not None):
            return job
        threading.Event().wait(0.005)
    pytest.fail(f"job did not become {status}: {manager.get(job_id)}")


class _Process:
    pid = 424242

    def __init__(self, release, started, stdout='{"answer":42}', stderr=""):
        self.release, self.started = release, started
        self.stdout, self.stderr = StringIO(stdout), StringIO(stderr)
        self.returncode = None

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.started.set()
        if timeout is None:
            assert self.release.wait(2)
            if self.returncode is None:
                self.returncode = 0
        else:
            self.returncode = -signal.SIGTERM
            self.release.set()
        return self.returncode

    def terminate(self):
        self.wait()

    def kill(self):
        self.returncode = -signal.SIGKILL
        self.release.set()


@pytest.mark.parametrize(
    ("path", "asset", "content_type"),
    [("/", "index.html", "text/html"), ("/app.css", "app.css", "text/css"), ("/app.js", "app.js", "text/javascript")],
)
def test_fixed_assets(path, asset, content_type):
    status, headers, body = _request(web.make_handler(web.JobManager()), "GET", path)

    assert status == 200
    assert headers["content-type"].startswith(content_type)
    assert body == resources.files("oeis_matcher").joinpath("web_assets", asset).read_bytes()


def test_home_exposes_every_workflow_and_search_profile():
    parser = _UIParser()
    parser.feed(resources.files("oeis_matcher").joinpath("web_assets", "index.html").read_text())

    assert parser.commands == web.COMMANDS
    assert parser.profiles == {"fast", "deep", "max"}
    assert {"/app.css", "/app.js"} <= parser.assets


def test_every_analyze_expert_control_has_hover_help():
    parser = _UIParser()
    parser.feed(resources.files("oeis_matcher").joinpath("web_assets", "index.html").read_text())

    assert parser.expert_labels == parser.expert_controls == 41
    assert len(parser.expert_help) == parser.expert_labels


def test_web_assets_are_package_data():
    project = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text())

    assert "web_assets/*" in project["tool"]["setuptools"]["package-data"]["oeis_matcher"]


@pytest.mark.parametrize("path", ["/../pyproject.toml", "/web_assets/index.html", "/app.css/../index.html"])
def test_assets_do_not_allow_arbitrary_paths(path):
    status, _, body = _request(web.make_handler(web.JobManager()), "GET", path)

    assert status == 404
    assert json.loads(body) == {"error": "not found"}


def test_status_route(monkeypatch):
    report = {"ready": True, "freshness": {"is_stale": False}, "paths": {"db": {"sequence_count": 7}}}
    monkeypatch.setattr(web, "_status", lambda: report)

    status, headers, body = _request(web.make_handler(web.JobManager()), "GET", "/api/status")

    assert status == 200
    assert headers["content-type"].startswith("application/json")
    assert json.loads(body) == report


@pytest.mark.parametrize(
    "headers",
    [
        {"Host": "evil.example"},
        {"Origin": "http://evil.example"},
        {"Origin": "http://127.0.0.1:9999"},
        {"Origin": "https://127.0.0.1"},
    ],
)
def test_routes_reject_non_loopback_host_or_origin(headers):
    status, _, body = _request(web.make_handler(web.JobManager()), "GET", "/", extra_headers=headers)

    assert status == 403
    assert json.loads(body) == {"error": "loopback Host and Origin required"}


@pytest.mark.parametrize(
    "headers",
    [
        {"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"},
        {"Host": "[::1]:8765", "Origin": "http://[::1]:8765"},
    ],
)
def test_routes_accept_matching_loopback_origin(headers):
    status, _, _ = _request(web.make_handler(web.JobManager()), "GET", "/", extra_headers=headers)

    assert status == 200


def test_job_start_poll_result_and_single_active(monkeypatch):
    release, started, calls = threading.Event(), threading.Event(), []
    process = _Process(release, started, stderr="diagnostic")

    def popen(argv, **kwargs):
        calls.append((argv, kwargs))
        return process

    monkeypatch.setattr(web.subprocess, "Popen", popen)
    manager = web.JobManager()
    handler = web.make_handler(manager)
    status, _, body = _request(handler, "POST", "/api/jobs", {"command": "analyze", "args": ["1,2,3", "--fast"]}, "application/json")
    job_id = json.loads(body)["id"]
    assert status == 202
    assert started.wait(1)

    status, _, body = _request(handler, "GET", f"/api/jobs/{job_id}")
    assert status == 200 and json.loads(body)["status"] == "running"
    status, _, body = _request(handler, "POST", "/api/jobs", {"command": "status"}, "application/json")
    assert status == 409 and "already running" in json.loads(body)["error"]

    release.set()
    job = _wait_for(manager, job_id, "completed")
    assert job["output"] == {"answer": 42}
    assert job["output_type"] == "json"
    assert job["stderr"] == "diagnostic"
    assert calls[0][0] == [sys.executable, "-m", "oeis_matcher.cli", "analyze", "1,2,3", "--fast", "--json"]
    status, _, body = _request(handler, "GET", f"/api/jobs/{job_id}")
    assert status == 200 and json.loads(body)["returncode"] == 0


@pytest.mark.parametrize(
    ("body", "content_type", "expected"),
    [
        ({}, "text/plain", 415),
        (b"{", "application/json", 400),
        (b"", "application/json", 413),
        (b"x" * (web.MAX_BODY + 1), "application/json", 413),
        ([], "application/json", 400),
        ({"args": []}, "application/json", 400),
        ({"command": "nope"}, "application/json", 400),
        ({"command": "status", "args": "--json"}, "application/json", 400),
        ({"command": "status", "args": [1]}, "application/json", 400),
        ({"command": "status", "args": ["bad\0arg"]}, "application/json", 400),
    ],
)
def test_job_request_validation(body, content_type, expected):
    status, headers, payload = _request(web.make_handler(web.JobManager()), "POST", "/api/jobs", body, content_type)

    assert status == expected
    assert headers["content-type"].startswith("application/json")
    assert isinstance(json.loads(payload)["error"], str)


def test_delete_cancels_running_job_and_keeps_output(monkeypatch):
    release, started = threading.Event(), threading.Event()
    process = _Process(release, started, stdout="partial output\n", stderr="stopped")
    signals = []
    monkeypatch.setattr(web.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(web.os, "killpg", lambda pid, sig: signals.append((pid, sig)))
    manager = web.JobManager()
    handler = web.make_handler(manager)
    _, _, body = _request(handler, "POST", "/api/jobs", {"command": "analyze", "args": ["1,2,3"]}, "application/json")
    job_id = json.loads(body)["id"]
    assert started.wait(1)

    status, _, body = _request(handler, "DELETE", f"/api/jobs/{job_id}")

    assert status == 200 and json.loads(body)["status"] == "cancelled"
    job = _wait_for(manager, job_id, "cancelled", settled=True)
    assert job["output"] == "partial output\n"
    assert job["output_type"] == "text"
    assert manager.list()["active_job_id"] is None
    if web.os.name != "nt":
        assert signals == [(process.pid, signal.SIGTERM)]


def test_cancel_during_process_spawn_stops_the_child(monkeypatch):
    spawn_entered, finish_spawn = threading.Event(), threading.Event()
    process = _Process(threading.Event(), threading.Event())
    signals = []

    def popen(*args, **kwargs):
        spawn_entered.set()
        assert finish_spawn.wait(2)
        return process

    monkeypatch.setattr(web.subprocess, "Popen", popen)
    monkeypatch.setattr(web.os, "killpg", lambda pid, sig: signals.append((pid, sig)))
    manager = web.JobManager()
    job_id = manager.start("status", [])["id"]
    assert spawn_entered.wait(1)
    cancelled, done = {}, threading.Event()

    def cancel():
        cancelled.update(manager.cancel(job_id))
        done.set()

    canceller = threading.Thread(target=cancel)
    canceller.start()
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        with manager.lock:
            if manager.jobs[job_id]["cancel_requested"]:
                break
        threading.Event().wait(0.005)
    else:
        pytest.fail("cancellation was not requested")
    finish_spawn.set()

    assert done.wait(2)
    canceller.join()
    assert cancelled["status"] == "cancelled"
    assert manager.list()["active_job_id"] is None
    if web.os.name != "nt":
        assert signals == [(process.pid, signal.SIGTERM)]


def test_manager_close_cancels_active_job(monkeypatch):
    release, started = threading.Event(), threading.Event()
    process = _Process(release, started)
    monkeypatch.setattr(web.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(web.os, "killpg", lambda *_: None)
    manager = web.JobManager()
    job = manager.start("status", [])
    assert started.wait(1)

    manager.close()

    assert manager.get(job["id"])["status"] == "cancelled"
    assert manager.list()["active_job_id"] is None
    assert manager.workers == {}
    with pytest.raises(RuntimeError, match="shutting down"):
        manager.start("status", [])


def test_json_responses_preserve_large_integers_and_normalize_nonfinite_values(monkeypatch):
    report = {"safe": 2**53 - 1, "large": 2**53, "negative": -(2**53), "values": [float("nan"), float("inf")]}
    monkeypatch.setattr(web, "_status", lambda: report)

    _, _, body = _request(web.make_handler(web.JobManager()), "GET", "/api/status")

    assert b"NaN" not in body and b"Infinity" not in body
    assert json.loads(body) == {"safe": 2**53 - 1, "large": str(2**53), "negative": str(-(2**53)), "values": [None, None]}


def test_job_output_is_capped(monkeypatch):
    monkeypatch.setattr(web, "MAX_OUTPUT", 8)
    release = threading.Event()
    release.set()
    process = _Process(release, threading.Event(), stdout="0123456789", stderr="abcdefghij")
    monkeypatch.setattr(web.subprocess, "Popen", lambda *args, **kwargs: process)
    manager = web.JobManager()

    job = _wait_for(manager, manager.start("status", [])["id"], "completed")

    assert job["output"] == "01234567"
    assert job["stderr"] == "abcdefgh"
    assert job["output_truncated"] is True


def test_json_flag_precedes_positional_separator(monkeypatch):
    release, started, calls = threading.Event(), threading.Event(), []
    release.set()

    def popen(argv, **_kwargs):
        calls.append(argv)
        return _Process(release, started)

    monkeypatch.setattr(web.subprocess, "Popen", popen)
    manager = web.JobManager()
    job = manager.start("analyze", ["--fast", "--", "-1,-2,-3"])
    _wait_for(manager, job["id"], "completed")

    assert calls == [[sys.executable, "-m", "oeis_matcher.cli", "analyze", "--fast", "--json", "--", "-1,-2,-3"]]


def test_browser_launch_uses_windows_host_under_wsl(monkeypatch):
    calls, launched = [], threading.Event()

    def popen(argv, **kwargs):
        calls.append((argv, kwargs))
        launched.set()
        return object()

    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")
    monkeypatch.setattr(web.subprocess, "Popen", popen)
    web._open_browser("http://127.0.0.1:8765/")

    assert launched.wait(1)
    assert calls[0][0] == ["cmd.exe", "/c", "start", "", "http://127.0.0.1:8765/"]
    assert calls[0][1]["stdout"] == web.subprocess.DEVNULL
    assert calls[0][1]["stderr"] == web.subprocess.DEVNULL


def test_serve_handles_termination_and_cleans_up(monkeypatch):
    events = []

    class Manager:
        def close(self):
            events.append("manager.close")

    class Server:
        server_port = 8765

        def serve_forever(self):
            handlers[signal.SIGTERM](signal.SIGTERM, None)

        def server_close(self):
            events.append("server.close")

    manager, server = Manager(), Server()
    originals = {signal.SIGTERM: object()}
    if hasattr(signal, "SIGHUP"):
        originals[signal.SIGHUP] = object()
    handlers = dict(originals)

    def set_handler(sig, handler):
        previous = handlers[sig]
        handlers[sig] = handler
        return previous

    monkeypatch.setattr(web, "JobManager", lambda: manager)
    monkeypatch.setattr(web, "make_server", lambda *_args, **_kwargs: server)
    monkeypatch.setattr(web.signal, "signal", set_handler)

    web.serve(open_browser=False)

    assert handlers == originals
    assert events == ["manager.close", "server.close"]
