"""Entrypoint smoke tests: ``py app.py`` must actually run (see brief APPMAIN).

Regression: app.py defined main() but had no ``__main__`` guard, so every
command-line invocation exited silently. The subprocess test proves the real
process answers; the static test pins the guard itself.
"""

import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path

APP_PATH = Path(__file__).resolve().parent.parent / "app.py"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _py_launcher():
    """Return a launcher for a modern Python, or None if unavailable."""
    for candidate in (sys.executable, "py", "python"):
        try:
            probe = subprocess.run(
                [candidate, "-c", "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"],
                capture_output=True, timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if probe.returncode == 0:
            return candidate
    return None


class TestEntrypoint(unittest.TestCase):
    def test_main_guard_exists(self) -> None:
        source = APP_PATH.read_text(encoding="utf-8")
        self.assertIn('if __name__ == "__main__":', source)
        self.assertIn("main()", source)

    def test_serve_api_process_responds(self) -> None:
        launcher = _py_launcher()
        if launcher is None:
            self.skipTest("no launchable Python >= 3.10 in this environment")
        port = _free_port()
        proc = subprocess.Popen(
            [launcher, str(APP_PATH), "--serve-api", "--port", str(port),
             "--host", "127.0.0.1"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            self._poll_until_responds(port)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)

    def _poll_until_responds(self, port: int) -> None:
        import urllib.error
        import urllib.request

        url = f"http://127.0.0.1:{port}/api/draft"
        deadline = time.monotonic() + 15
        last_error = None
        while time.monotonic() < deadline:
            try:
                # Bad JSON body must come back as a 400 from the live process.
                request = urllib.request.Request(
                    url, data=b"{not json",
                    headers={"Content-Type": "application/json"}, method="POST",
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    self.assertEqual(response.status, 200)
                return
            except urllib.error.HTTPError as exc:
                self.assertEqual(exc.code, 400)
                return
            except (OSError, urllib.error.URLError) as exc:
                last_error = exc
                time.sleep(0.3)
        self.fail(f"app.py --serve-api never answered on port {port}: {last_error}")


if __name__ == "__main__":
    unittest.main()
