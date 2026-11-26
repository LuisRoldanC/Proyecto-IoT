import argparse
import json
import random
import time
import psutil
import paho.mqtt.client as mqtt


def read_cpu_temp_c() -> float:
    """Lee la temperatura real si el SO la expone, si no, se estima según uso de CPU"""
    if hasattr(psutil, "sensors_temperatures"):
        try:
            temps = psutil.sensors_temperatures()
            for entries in (temps or {}).values():
                if entries and entries[0].current is not None:
                    return round(float(entries[0].current), 2)
        except Exception:
            pass
    # para Windows estima temperatura con base en el uso real de CPU
    cpu_pct = psutil.cpu_percent(interval=None)
    return round(45.0 + (cpu_pct * 0.45) + random.uniform(-1.5, 1.5), 2)


def main():
    parser = argparse.ArgumentParser(description="Publicador MQTT de temperatura de CPU")
    parser.add_argument("--broker", default="test.mosquitto.org", help="Host del broker MQTT")
    parser.add_argument("--port", type=int, default=1883, help="Puerto MQTT")
    parser.add_argument("--topic", default="proyecto_iot/cpu/temp", help="Tópico MQTT") # Tópico para publicar la temperatura de la CPU
    parser.add_argument("--arch", choices=["local", "cloud"], default="cloud", help="Arquitectura a etiquetar")
    parser.add_argument("--interval", type=float, default=1.0, help="Segundos entre envíos")
    parser.add_argument("--count", type=int, default=30, help="Número de mensajes a enviar (0 = infinito)")
    parser.add_argument("--qos", type=int, choices=[0, 1, 2], default=1, help="Nivel QoS de MQTT")
    args = parser.parse_args()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(args.broker, args.port, keepalive=60)
    client.loop_start()

    # Primera lectura de cpu_percent para inicializar psutil
    psutil.cpu_percent(interval=None)

    print(f"Publicando en {args.broker}:{args.port} | tópico: {args.topic} | arch: {args.arch}")
    seq = 1
    try:
        while args.count == 0 or seq <= args.count:
            payload = {
                "seq": seq,
                "arch": args.arch,
                "temp_c": read_cpu_temp_c(),
                "sent_ts_ms": time.time() * 1000.0,
            }
            client.publish(args.topic, json.dumps(payload), qos=args.qos)
            print(f"[{seq}] {payload['temp_c']} °C enviado")
            seq += 1
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nPublicador detenido.")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()