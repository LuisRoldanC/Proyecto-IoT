import os

from paho.mqtt.client import Client


def configure_client(client: Client) -> None:
    username = os.environ.get("MQTT_USERNAME")
    password = os.environ.get("MQTT_PASSWORD")
    if username is not None or password is not None:
        client.username_pw_set(username or "", password)

    tls_value = os.environ.get("MQTT_TLS", "false").strip().lower()
    if tls_value not in {"true", "false", "1", "0", "yes", "no"}:
        raise ValueError("MQTT_TLS debe ser true o false.")
    if tls_value in {"true", "1", "yes"}:
        client.tls_set()
