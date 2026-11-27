# Monitor QoS / QoE de CPU

Dashboard para comparar temperatura y calidad de servicio entre procesamiento local y en la nube. Incluye escenarios normales, estrés de CPU y congestión de red.

## Dashboard

![Resumen del monitoreo térmico de CPU](dashboard_img.png)

![Comparación QoE y resultados por escenario](dashboard_img2.png)

## Publicar en Render

Despliega como **Web Service** mediante **New > Blueprint**. Render detectará
`render.yaml`; durante la configuración define un valor secreto para
`CONTROL_TOKEN`. La compilación genera el dashboard y los resultados simulados;
al iniciar `server.py`, el publicador y el suscriptor MQTT arrancan dentro del
mismo proceso. No se necesitan comandos de inicio adicionales.

La captura empieza automáticamente en cada despliegue o reinicio del servicio.
En el dashboard, escribe el mismo `CONTROL_TOKEN` para consultar su estado o
detenerla y volverla a iniciar. La página consulta las métricas en vivo cada
2 segundos; Render publica una muestra cada 0.5 segundos.

Render configura por defecto `test.mosquitto.org` con MQTT sobre TLS (puerto
8883), tópico `proyecto_iot/cpu/temp` y QoS 1. Para usar otro broker, cambia
`MQTT_BROKER`, `MQTT_PORT`, `MQTT_TOPIC`, `MQTT_QOS` y `MQTT_INTERVAL` en las
variables de entorno del servicio. Configura `MQTT_TLS=true` si el broker usa
TLS; para brokers con autenticación, añade `MQTT_USERNAME` y `MQTT_PASSWORD`
como variables secretas.
Guarda los cambios y vuelve a desplegar. No pongas credenciales en el dashboard.

El broker público es compartido; usa un tópico propio y un broker con
autenticación para datos privados. Si Render reinicia el servicio, la captura
MQTT se inicia automáticamente.

Los escenarios simulados se regeneran cada segundo y también al actualizar el
dashboard. La captura MQTT en vivo se actualiza al recibir mensajes del broker.

## Requisitos
- Python 3.10 o superior
- Dependencias en `requirements.txt` (`psutil`, `paho-mqtt`):
```bash
pip install -r requirements.txt
```

## Ejecutar

### 1. Simulación (escenarios reproducibles)
Desde esta carpeta, genera los resultados e inicia un servidor local:

```bash
python sim_qos_qoe.py
python -m http.server 8000
```
### 2. Servidor y captura en vivo MQTT
Inicia el servidor y la captura desde un solo comando:
```bash
python server.py
```
Abre [http://localhost:8000/dashboard.html](http://localhost:8000/dashboard.html).
La captura comienza junto con el servidor.

Para pruebas locales, el publicador y el suscriptor también se pueden ejecutar
por separado; sus opciones se mantienen disponibles en `publisher.py` y
`subscriber.py`.
Por defecto se conectan al broker público `test.mosquitto.org` por el puerto
1883 (sin TLS), etiquetado como `cloud`. Se puede cambiar broker, tópico o
arquitectura con argumentos:
```bash
python publisher.py --broker localhost --arch local --count 20
```
También se pueden configurar `MQTT_BROKER`, `MQTT_PORT`, `MQTT_TOPIC`,
`MQTT_QOS`, `MQTT_INTERVAL`, `MQTT_TLS`, `MQTT_USERNAME` y `MQTT_PASSWORD`
mediante variables de entorno. Para un broker local, deja `MQTT_TLS=false`
(valor predeterminado).
> `psutil.sensors_temperatures()` solo está disponible en Linux. En Windows, `publisher.py` estima la temperatura a partir del uso real de CPU (`psutil.cpu_percent()`).

### 3. Dashboard sin captura MQTT
Para mostrar solo resultados simulados, inicia un servidor estático:
```bash
python -m http.server 8000
```
Abre [http://localhost:8000/dashboard.html](http://localhost:8000/dashboard.html).
