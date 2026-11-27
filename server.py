import hmac
import json
import math
import os
import random
import threading
import time
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import paho.mqtt.client as mqtt
import psutil

from mqtt_config import configure_client
from sim_qos_qoe import compute_qoe


ROOT = Path(__file__).resolve().parent
PUBLIC_DIR = ROOT / "public"
LIVE_STATS_FILE = PUBLIC_DIR / "results" / "cpu_qos_qoe.json"


def new_bucket() -> dict:
    return {
        "latency_mean_ms": 0.0,
        "latency_m2_ms": 0.0,
        "temp_mean_c": 0.0,
        "max_temp_c": 0.0,
        "last_temp_c": 0.0,
        "history": [],
        "received": 0,
        "max_seq": 0,
        "delayed_alerts": 0,
    }


def read_cpu_temp_c() -> float:
    if hasattr(psutil, "sensors_temperatures"):
        try:
            temperatures = psutil.sensors_temperatures()
            for entries in (temperatures or {}).values():
                for entry in entries:
                    if entry.current is None:
                        continue
                    temperature = float(entry.current)
                    if math.isfinite(temperature) and 0 <= temperature <= 150:
                        return round(temperature, 2)
        except (NotImplementedError, OSError, RuntimeError, TypeError, ValueError):
            pass
    cpu_pct = psutil.cpu_percent(interval=None)
    return round(45.0 + cpu_pct * 0.45 + random.uniform(-1.5, 1.5), 2)


class CaptureManager:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.data_lock = threading.Lock()
        self.publisher: mqtt.Client | None = None
        self.subscriber: mqtt.Client | None = None
        self.publisher_thread: threading.Thread | None = None
        self.stop_event: threading.Event | None = None
        self.started = False
        self.state: dict[str, dict] = {}
        self.broker = os.environ.get("MQTT_BROKER", "test.mosquitto.org")
        self.port = int(os.environ.get("MQTT_PORT", "1883"))
        self.topic = os.environ.get("MQTT_TOPIC", "proyecto_iot/cpu/temp")
        self.qos = int(os.environ.get("MQTT_QOS", "1"))
        self.interval = float(os.environ.get("MQTT_INTERVAL", "0.5"))
        self.arch = os.environ.get("MQTT_ARCH", "cloud")

    def _status_locked(self) -> dict[str, bool]:
        return {
            "publisher": self.started and self.publisher is not None,
            "subscriber": self.started and self.subscriber is not None,
        }

    def status(self) -> dict[str, bool]:
        with self.lock:
            return self._status_locked()

    def _save_stats_locked(self) -> None:
        summary = {}
        for arch, bucket in self.state.items():
            if not bucket["received"]:
                continue
            avg_lat = bucket["latency_mean_ms"]
            jitter = math.sqrt(
                max(0.0, bucket["latency_m2_ms"] / (bucket["received"] - 1))
            ) if bucket["received"] > 1 else 0.0
            lost = max(0, bucket["max_seq"] - bucket["received"])
            loss_pct = (lost / bucket["max_seq"]) * 100.0 if bucket["max_seq"] else 0.0

            summary[arch] = {
                "samples": bucket["received"],
                "last_cpu_temp_c": round(bucket["last_temp_c"], 2),
                "avg_cpu_temp_c": round(bucket["temp_mean_c"], 2),
                "max_cpu_temp_c": round(bucket["max_temp_c"], 2),
                "avg_latency_ms": round(avg_lat, 2),
                "jitter_ms": round(jitter, 2),
                "packet_loss_pct": round(loss_pct, 2),
                "delayed_alerts": bucket["delayed_alerts"],
                "qoe_score": compute_qoe(avg_lat, jitter, loss_pct, bucket["delayed_alerts"]),
                "history": bucket["history"][-30:],
            }

        LIVE_STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
        temp_path = LIVE_STATS_FILE.with_suffix(".json.tmp")
        with temp_path.open("w", encoding="utf-8") as output:
            json.dump(summary, output, indent=2)
        for attempt in range(3):
            try:
                os.replace(temp_path, LIVE_STATS_FILE)
                break
            except PermissionError:
                if attempt == 2:
                    raise
                time.sleep(0.02 * (attempt + 1))

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code != 0:
            print(f"Error al conectar con MQTT ({reason_code})", flush=True)
            return
        print(f"Conectado a {self.broker}:{self.port}", flush=True)
        if client is self.subscriber:
            result, _ = client.subscribe(self.topic, qos=self.qos)
            if result != mqtt.MQTT_ERR_SUCCESS:
                print(f"No se pudo suscribir al tópico {self.topic} (código {result})", flush=True)
            else:
                print(f"Escuchando tópico: {self.topic}", flush=True)

    def _on_message(self, client, userdata, message) -> None:
        recv_ts_ms = time.time() * 1000.0
        try:
            data = json.loads(message.payload.decode("utf-8"))
            arch = str(data.get("arch", "cloud")).lower()
            seq = int(data["seq"])
            temp_c = float(data["temp_c"])
            sent_ts_ms = float(data["sent_ts_ms"])
            if arch not in {"local", "cloud"} or seq < 1:
                raise ValueError("arquitectura o secuencia inválida")
            if (
                not math.isfinite(temp_c)
                or not math.isfinite(sent_ts_ms)
                or not 0 <= temp_c <= 150
            ):
                raise ValueError("temperatura o marca de tiempo no válida")
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, KeyError, TypeError) as error:
            print(f"Mensaje MQTT ignorado ({error})", flush=True)
            return

        latency_ms = max(0.0, recv_ts_ms - sent_ts_ms)
        with self.data_lock:
            if arch not in self.state or seq == 1:
                self.state[arch] = new_bucket()
            bucket = self.state[arch]
            previous_count = bucket["received"]
            bucket["received"] += 1
            bucket["max_seq"] = max(bucket["max_seq"], seq)
            latency_delta = latency_ms - bucket["latency_mean_ms"]
            bucket["latency_mean_ms"] += latency_delta / bucket["received"]
            bucket["latency_m2_ms"] += latency_delta * (
                latency_ms - bucket["latency_mean_ms"]
            )
            temp_delta = temp_c - bucket["temp_mean_c"]
            bucket["temp_mean_c"] += temp_delta / bucket["received"]
            bucket["max_temp_c"] = max(bucket["max_temp_c"], temp_c) if previous_count else temp_c
            bucket["last_temp_c"] = temp_c
            if temp_c >= 85.0 and latency_ms > 150.0:
                bucket["delayed_alerts"] += 1
            bucket["history"].append({
                "ts": datetime.now().strftime("%H:%M:%S"),
                "temp_c": round(temp_c, 2),
                "latency_ms": round(latency_ms, 2),
            })
            bucket["history"] = bucket["history"][-30:]
            try:
                self._save_stats_locked()
            except OSError as error:
                print(f"No se pudieron guardar las métricas MQTT: {error}", flush=True)
        print(f"[{arch} #{seq}] {temp_c:.2f} °C | latencia: {latency_ms:.1f} ms", flush=True)

    def _publish_loop(self, client: mqtt.Client, stop_event: threading.Event) -> None:
        psutil.cpu_percent(interval=None)
        seq = 1
        while not stop_event.is_set():
            if client.is_connected():
                payload = {
                    "seq": seq,
                    "arch": self.arch,
                    "temp_c": read_cpu_temp_c(),
                    "sent_ts_ms": time.time() * 1000.0,
                }
                info = client.publish(self.topic, json.dumps(payload), qos=self.qos)
                if info.rc == mqtt.MQTT_ERR_SUCCESS:
                    print(f"[{seq}] {payload['temp_c']} °C enviado", flush=True)
                    seq += 1
                else:
                    print(f"No se pudo publicar en MQTT (código {info.rc})", flush=True)
            stop_event.wait(self.interval)

    def start(self) -> dict[str, bool]:
        with self.lock:
            if self.started:
                return self._status_locked()

            if not self.broker or not 1 <= self.port <= 65535:
                raise ValueError("MQTT_BROKER o MQTT_PORT no son válidos.")
            if (
                not self.topic
                or self.qos not in (0, 1, 2)
                or self.interval <= 0
                or not math.isfinite(self.interval)
                or self.arch not in {"local", "cloud"}
            ):
                raise ValueError("MQTT_TOPIC, MQTT_QOS, MQTT_INTERVAL o MQTT_ARCH no son válidos.")

            self.stop_event = threading.Event()
            self.state = {}
            try:
                with self.data_lock:
                    self._save_stats_locked()

                self.subscriber = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
                self.publisher = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
                configure_client(self.subscriber)
                configure_client(self.publisher)
                self.subscriber.on_connect = self._on_connect
                self.subscriber.on_message = self._on_message
                self.subscriber.connect_async(self.broker, self.port, keepalive=60)
                self.publisher.connect_async(self.broker, self.port, keepalive=60)
                for client in (self.subscriber, self.publisher):
                    result = client.loop_start()
                    if result != mqtt.MQTT_ERR_SUCCESS:
                        raise RuntimeError(f"No se pudo iniciar el bucle MQTT (código {result}).")

                self.started = True
                self.publisher_thread = threading.Thread(
                    target=self._publish_loop,
                    args=(self.publisher, self.stop_event),
                    name="mqtt-publisher",
                    daemon=True,
                )
                self.publisher_thread.start()
            except (OSError, RuntimeError, ValueError):
                self._stop_locked()
                raise
            print(f"Captura MQTT iniciada para {self.broker}:{self.port}", flush=True)
            return self._status_locked()

    def _stop_locked(self) -> None:
        if self.stop_event is not None:
            self.stop_event.set()
        if self.publisher_thread is not None:
            self.publisher_thread.join(timeout=5)
        for client in (self.publisher, self.subscriber):
            if client is not None:
                client.disconnect()
                client.loop_stop()
        self.publisher = None
        self.subscriber = None
        self.publisher_thread = None
        self.stop_event = None
        self.started = False

    def stop(self) -> dict[str, bool]:
        with self.lock:
            self._stop_locked()
            print("Captura MQTT detenida", flush=True)
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
        path = urlsplit(self.path).path
        if path == "/":
            self.send_response(302)
            self.send_header("Location", "/dashboard.html")
            self.end_headers()
            return
        if path == "/api/status":
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
        except (OSError, RuntimeError, ValueError) as error:
            self._send_json(500, {"error": f"No se pudo controlar MQTT: {error}"})
            return
        self._send_json(200, status)


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), DashboardHandler)
    try:
        try:
            CAPTURE_MANAGER.start()
        except (OSError, RuntimeError, ValueError) as error:
            print(f"No se pudo iniciar la captura MQTT: {error}", flush=True)
        print(f"Dashboard escuchando en el puerto {port}", flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        CAPTURE_MANAGER.stop()


if __name__ == "__main__":
    main()
