import hmac
import json
import os
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent
PUBLIC_DIR = ROOT / "public"


class CaptureManager:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.publisher: subprocess.Popen | None = None
        self.subscriber: subprocess.Popen | None = None

    def _clear_finished(self) -> None:
        if self.publisher is not None and self.publisher.poll() is not None:
            self.publisher = None
        if self.subscriber is not None and self.subscriber.poll() is not None:
            self.subscriber = None

    def _status_locked(self) -> dict[str, bool]:
        return {
            "publisher": self.publisher is not None,
            "subscriber": self.subscriber is not None,
        }

    def status(self) -> dict[str, bool]:
        with self.lock:
            self._clear_finished()
            return self._status_locked()

    def _launch(self, script: str, *args: str) -> subprocess.Popen:
        return subprocess.Popen(
            [sys.executable, str(ROOT / script), *args],
            cwd=PUBLIC_DIR,
            stdin=subprocess.DEVNULL,
        )

    @staticmethod
    def _stop_process(process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return
        try:
            process.terminate()
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    def start(self) -> dict[str, bool]:
        with self.lock:
            self._clear_finished()
            started = []
            try:
                if self.subscriber is None:
                    self.subscriber = self._launch("subscriber.py")
                    started.append(("subscriber", self.subscriber))
                if self.publisher is None:
                    self.publisher = self._launch("publisher.py", "--count", "0")
                    started.append(("publisher", self.publisher))
            except OSError:
                for name, process in reversed(started):
                    self._stop_process(process)
                    setattr(self, name, None)
                raise
            self._clear_finished()
            return self._status_locked()

    def stop(self) -> dict[str, bool]:
        with self.lock:
            errors = []
            for name in ("publisher", "subscriber"):
                process = getattr(self, name)
                if process is not None:
                    try:
                        self._stop_process(process)
                    except (OSError, subprocess.TimeoutExpired) as error:
                        errors.append(str(error))
                    if process.poll() is not None:
                        setattr(self, name, None)
            if errors:
                raise RuntimeError("; ".join(errors))
            self._clear_finished()
            return self._status_locked()


CAPTURE_MANAGER = CaptureManager()


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC_DIR), **kwargs)

    def _send_json(self, status_code: int, payload: dict) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _authorized(self) -> bool:
        expected = os.environ.get("CONTROL_TOKEN", "")
        if not expected:
            self._send_json(503, {"error": "CONTROL_TOKEN no está configurado en Render."})
            return False
        supplied = self.headers.get("Authorization", "")
        if not hmac.compare_digest(supplied, f"Bearer {expected}"):
            self._send_json(401, {"error": "Token de control inválido."})
            return False
        return True

    def do_GET(self) -> None:
        if urlsplit(self.path).path == "/api/status":
            if self._authorized():
                self._send_json(200, CAPTURE_MANAGER.status())
            return
        super().do_GET()

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if path not in ("/api/start", "/api/stop"):
            self._send_json(404, {"error": "Ruta no encontrada."})
            return
        if not self._authorized():
            return

        try:
            status = CAPTURE_MANAGER.start() if path == "/api/start" else CAPTURE_MANAGER.stop()
        except (OSError, RuntimeError) as error:
            self._send_json(500, {"error": f"No se pudieron controlar los procesos: {error}"})
            return
        self._send_json(200, status)


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), DashboardHandler)
    print(f"Dashboard escuchando en el puerto {port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        CAPTURE_MANAGER.stop()


if __name__ == "__main__":
    main()
