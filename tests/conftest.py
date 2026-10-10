"""The entire pytest suite must work without networking."""

import os
import socket
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        # Browsers request this on their own. A quiet success avoids a
        # console error that the network guard would treat as a page failure.
        if self.path.split("?", 1)[0] == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        super().do_GET()


@pytest.fixture(autouse=True)
def deny_network(monkeypatch, request):
    if request.node.get_closest_marker("e2e"):
        return

    def denied(*args, **kwargs):
        raise AssertionError("Tests may not open network connections")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)


@pytest.fixture(scope="session")
def explorer_server():
    """Serve web/ on a free loopback port for browser tests."""
    web = Path(__file__).resolve().parents[1] / "web"
    handler = partial(QuietHandler, directory=str(web))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    thread.join(timeout=3)
    server.server_close()


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: browser end-to-end test")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.skipped:
        skipped = item.session.__dict__.setdefault("cubs_skipped", {})
        skipped[item.nodeid] = bool(item.get_closest_marker("e2e"))


def pytest_sessionfinish(session, exitstatus):
    """Print the skip count; with CUBS_REQUIRE_E2E=1 a skipped e2e fails."""
    skipped = session.__dict__.get("cubs_skipped", {})
    message = f"\nSkipped tests: {len(skipped)}\n"
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        reporter.write(message)
    else:
        print(message, end="")
    if os.environ.get("CUBS_REQUIRE_E2E") == "1":
        e2e_skips = [
            name for name, is_e2e in skipped.items() if is_e2e
        ]
        if e2e_skips:
            detail = f"CUBS_REQUIRE_E2E=1 but e2e skipped: {e2e_skips}\n"
            if reporter is not None:
                reporter.write(detail)
            else:
                print(detail, end="")
            session.exitstatus = 1
