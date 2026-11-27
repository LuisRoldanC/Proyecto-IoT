# Monitor QoS / QoE de CPU

Dashboard para comparar temperatura y calidad de servicio entre procesamiento local y en la nube. Incluye escenarios normales, estrés de CPU y congestión de red.

## Dashboard

![Resumen del monitoreo térmico de CPU](dashboard_img.png)

![Comparación QoE y resultados por escenario](dashboard_img2.png)

## Publicar en Render

Para controlar MQTT desde el dashboard, despliega como **Web Service** mediante
**New > Blueprint**. Render detectará `render.yaml`; durante la configuración
define un valor secreto para `CONTROL_TOKEN`. El servicio ejecuta `server.py` y
Render inicia la compilación con `render_build.py`.

En el dashboard, escribe el mismo `CONTROL_TOKEN` y usa **Iniciar captura** o
**Detener captura**. El botón inicia o detiene juntos `subscriber.py` y
`publisher.py`; el publicador permanece activo hasta detenerlo. La página consulta
las métricas en vivo cada 10 segundos.

El sistema usa el broker MQTT público configurado por defecto en ambos scripts.
Si Render reinicia el servicio, vuelve a abrir el dashboard e inicia la captura
otra vez cuando la necesites.

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
### 2. Captura en vivo por MQTT (Opcional)
Abrir dos terminales en la carpeta del proyecto:
```bash
# Terminal 1: suscriptor (calcula QoS/QoE y guarda results/cpu_qos_qoe.json)
python subscriber.py
# Terminal 2: publicador (envía lecturas de temperatura por MQTT)
python publisher.py --count 20
```
Por defecto se conectan al broker público `test.mosquitto.org` (etiquetado como `cloud`). Se puede cambiar broker, tópico o arquitectura con argumentos:
```bash
python publisher.py --broker localhost --arch local --count 20
```
> `psutil.sensors_temperatures()` solo está disponible en Linux. En Windows, `publisher.py` estima la temperatura a partir del uso real de CPU (`psutil.cpu_percent()`).

### 3. Dashboard web
Inicia un servidor local:
```bash
python -m http.server 8000
```

Abre [http://localhost:8000/dashboard.html](http://localhost:8000/dashboard.html). 
