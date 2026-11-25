import argparse
import csv
import json
import os
import random
import statistics
from datetime import datetime, timezone

RESULTS_DIR = "results"
REAL_STATS_FILE = os.path.join(RESULTS_DIR, "cpu_qos_qoe.json")


def compute_qoe(avg_lat_ms: float, jitter_ms: float, loss_pct: float, delayed_alerts: int) -> float:
    penalty = (avg_lat_ms * 0.12) + (jitter_ms * 0.25) + (loss_pct * 2.5) + (delayed_alerts * 5.0)
    return round(max(0.0, min(100.0, 100.0 - penalty)), 2)


def simulate_scenario(arch: str, scenario: str, samples: int = 60, seed: int = 42) -> dict:
    rng = random.Random(f"{seed}-{arch}-{scenario}")

    profiles = {
        "local": {
            "normal":        {"lat_base": 12.0,  "lat_jit": 3.0,  "loss": 0.0, "temp_base": 52.0, "spike_prob": 0.03},
            "estres_cpu":    {"lat_base": 18.0,  "lat_jit": 5.0,  "loss": 0.2, "temp_base": 86.0, "spike_prob": 0.35},
            "congestion_red":{"lat_base": 24.0,  "lat_jit": 8.0,  "loss": 0.5, "temp_base": 68.0, "spike_prob": 0.10},
        },
        "cloud": {
            "normal":        {"lat_base": 115.0, "lat_jit": 22.0, "loss": 1.2, "temp_base": 52.0, "spike_prob": 0.03},
            "estres_cpu":    {"lat_base": 165.0, "lat_jit": 38.0, "loss": 2.8, "temp_base": 86.0, "spike_prob": 0.35},
            "congestion_red":{"lat_base": 290.0, "lat_jit": 75.0, "loss": 6.5, "temp_base": 68.0, "spike_prob": 0.10},
        },
    }

    cfg = profiles[arch][scenario]
    latencies = []
    temps = []
    lost_packets = 0
    delayed_alerts = 0

    for _ in range(samples):
        temp = round(cfg["temp_base"] + rng.uniform(-3.0, 6.0) + (10.0 if rng.random() < cfg["spike_prob"] else 0.0), 2)
        temps.append(temp)

        if rng.random() < (cfg["loss"] / 100.0):
            lost_packets += 1
            continue

        lat = max(1.0, cfg["lat_base"] + rng.gauss(0.0, cfg["lat_jit"]))
        latencies.append(lat)

        # En monitoreo térmico de CPU, una alerta crítica (>= 85 °C) con más de 150 ms de latencia se considera tardía
        if temp >= 85.0 and lat > 150.0:
            delayed_alerts += 1

    avg_lat = statistics.mean(latencies) if latencies else 0.0
    jitter = statistics.stdev(latencies) if len(latencies) > 1 else 0.0
    loss_pct = (lost_packets / samples) * 100.0 if samples else 0.0
    qoe = compute_qoe(avg_lat, jitter, loss_pct, delayed_alerts)

    return {
        "architecture": arch,
        "scenario": scenario,
        "samples": samples,
        "avg_cpu_temp_c": round(statistics.mean(temps), 2),
        "max_cpu_temp_c": round(max(temps), 2),
        "avg_latency_ms": round(avg_lat, 2),
        "jitter_ms": round(jitter, 2),
        "packet_loss_pct": round(loss_pct, 2),
        "delayed_alerts": delayed_alerts,
        "qoe_score": qoe,
    }


def load_real_telemetry_if_available() -> dict | None:
    if not os.path.exists(REAL_STATS_FILE):
        return None
    try:
        with open(REAL_STATS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data:
            return data
    except (OSError, json.JSONDecodeError):
        return None
    return None


def main():
    parser = argparse.ArgumentParser(description="Simulador QoS/QoE para monitoreo de temperatura de CPU (Local vs. Nube)")
    parser.add_argument("--samples", type=int, default=60, help="Número de muestras por escenario simulado")
    parser.add_argument("--seed", type=int, default=42, help="Semilla aleatoria para reproducibilidad")
    args = parser.parse_args()

    os.makedirs(RESULTS_DIR, exist_ok=True)
    scenarios = ["normal", "estres_cpu", "congestion_red"]
    architectures = ["local", "cloud"]

    rows = []
    for scenario in scenarios:
        for arch in architectures:
            rows.append(simulate_scenario(arch, scenario, samples=args.samples, seed=args.seed))

    real_data = load_real_telemetry_if_available()

    output = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "simulated_scenarios": rows,
        "live_capture": real_data,
    }

    json_path = os.path.join(RESULTS_DIR, "simulation_summary.json")
    csv_path = os.path.join(RESULTS_DIR, "simulation_summary.csv")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    fieldnames = [
        "architecture", "scenario", "samples",
        "avg_cpu_temp_c", "max_cpu_temp_c",
        "avg_latency_ms", "jitter_ms", "packet_loss_pct",
        "delayed_alerts", "qoe_score"
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Simulación completada. Guardado en:\n - {json_path}\n - {csv_path}")
    if real_data:
        print(f" - Captura en vivo detectada desde {REAL_STATS_FILE}")


if __name__ == "__main__":
    main()