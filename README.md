# Monitor QoS / QoE de CPU

Dashboard para comparar temperatura y calidad de servicio entre procesamiento local y en la nube. Incluye escenarios normales, estrés de CPU y congestión de red.

## Dashboard

![Resumen del monitoreo térmico de CPU](dashboard_img.png)

![Comparación QoE y resultados por escenario](dashboard_img2.png)

## Ejecutar

Desde esta carpeta, genera los resultados e inicia un servidor local:

```bash
python sim_qos_qoe.py
python -m http.server 8000
```

Abre [http://localhost:8000/dashboard.html](http://localhost:8000/dashboard.html). 
