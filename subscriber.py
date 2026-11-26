import argparse
import json
import os
import statistics
import time
from datetime import datetime
import paho.mqtt.client as mqtt

from sim_qos_qoe import RESULTS_DIR, REAL_STATS_FILE, compute_qoe


def new_bucket() -> dict:
    return {
        "latencies": [],
        "temps": [],
        "history": [],
        "received": 0,
        "max_seq": 0,
        "delayed_alerts": 0,
    }


def save_stats(state: dict, output_path: str) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    summary = {}
    for arch, b in state.items():
        if not b["temps"]:
            continue
        avg_lat = statistics.mean(b["latencies"]) if b["latencies"] else 0.0
        jitter = statistics.stdev(b["latencies"]) if len(b["latencies"]) > 1 else 0.0
        lost = max(0, b["max_seq"] - b["received"])
        loss_pct = (lost / b["max_seq"]) * 100.0 if b["max_seq"] > 0 else 0.0
        qoe = compute_qoe(avg_lat, jitter, loss_pct, b["delayed_alerts"])

        summary[arch] = {
            "samples": b["received"],
            "last_cpu_temp_c": round(b["temps"][-1], 2),
            "avg_cpu_temp_c": round(statistics.mean(b["temps"]), 2),
            "max_cpu_temp_c": round(max(b["temps"]), 2),
            "avg_latency_ms": round(avg_lat, 2),
            "jitter_ms": round(jitter, 2),
            "packet_loss_pct": round(loss_pct, 2),
            "delayed_alerts": b["delayed_alerts"],
            "qoe_score": qoe,
            "history": b["history"][-30:],
        }

    tmp_path = output_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    os.replace(tmp_path, output_path)


def main():
    parser = argparse.ArgumentParser(description="Suscriptor MQTT para métricas QoS/QoE en vivo")
    parser.add_argument("--broker", default="test.mosquitto.org", help="Host del broker MQTT")
    parser.add_argument("--port", type=int, default=1883, help="Puerto MQTT")
    parser.add_argument("--topic", default="proyecto_iot/cpu/temp", help="Tópico MQTT")
    parser.add_argument("--qos", type=int, choices=[0, 1, 2], default=1, help="Nivel QoS de MQTT")
    args = parser.parse_args()

    os.makedirs(RESULTS_DIR, exist_ok=True)
    state: dict[str, dict] = {}

    def on_connect(client, userdata, flags, reason_code, properties):
        print(f"Conectado a {args.broker}:{args.port} (código: {reason_code})")
        client.subscribe(args.topic, qos=args.qos)
        print(f"Escuchando tópico: {args.topic} (Ctrl+C para detener)")

    def on_message(client, userdata, msg):
        recv_ts_ms = time.time() * 1000.0
        try:
            data = json.loads(msg.payload.decode("utf-8"))
            arch = str(data.get("arch", "cloud")).lower()
            seq = int(data["seq"])
            temp_c = float(data["temp_c"])
            sent_ts_ms = float(data["sent_ts_ms"])
        except (ValueError, KeyError, TypeError) as err:
            print(f"Mensaje ignorado ({err})")
            return

        # Si el publicador se reinició (seq == 1), reinicia el conteo de esa arquitectura
        if arch not in state or seq == 1:
            state[arch] = new_bucket()

        b = state[arch]
        latency_ms = max(0.0, recv_ts_ms - sent_ts_ms)
        b["received"] += 1
        b["max_seq"] = max(b["max_seq"], seq)
        b["temps"].append(temp_c)
        b["latencies"].append(latency_ms)
        if temp_c >= 85.0 and latency_ms > 150.0:
            b["delayed_alerts"] += 1

        b["history"].append({
            "ts": datetime.now().strftime("%H:%M:%S"),
            "temp_c": round(temp_c, 2),
            "latency_ms": round(latency_ms, 2),
        })

        save_stats(state, REAL_STATS_FILE)
        print(f"[{arch} #{seq}] {temp_c:.2f} °C | latencia: {latency_ms:.1f} ms")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(args.broker, args.port, keepalive=60)

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\nSuscriptor detenido.")
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()