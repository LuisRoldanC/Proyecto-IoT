# Monitor QoS / QoE de CPU

Dashboard para comparar temperatura y calidad de servicio entre procesamiento local y en la nube. Incluye escenarios normales, estrés de CPU y congestión de red.

## Dashboard

![Resumen del monitoreo térmico de CPU](dashboard_img.png)

![Comparación QoE y resultados por escenario](dashboard_img2.png)

## Publicar en Render

El dashboard se publica como un sitio estático. Render ejecuta `render_build.py`,
que genera los resultados simulados y prepara los archivos del dashboard; no hay
que agregar varios `.py` como comandos de inicio.

1. En Render, selecciona **New > Blueprint** y conecta este repositorio.
2. Render detectará `render.yaml`; confirma la creación del servicio.

La compilación ejecuta solo la simulación. `publisher.py` y `subscriber.py` son
opcionales para captura MQTT en vivo y no es necesario dejarlos ejecutándose para
mostrar el dashboard.

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
