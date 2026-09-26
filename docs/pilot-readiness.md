# Hoja de ruta del piloto sandbox

Esta hoja registra los ocho frentes acordados y sus condiciones verificables.

| Fase | Estado | Entregable verificable |
|---|---|---|
| 1. QC científico ampliado | implementado para ejecuciones nuevas | Seis láminas CONN por sujeto, ART, tSNR, DVARS, volúmenes retenidos y racha de outliers |
| 2. Recálculo por muestra | implementado | Tarea persistente que reutiliza primer nivel, exige QC completo y `n >= 2`, y conserva versiones anteriores |
| 3. Portal de revisión | implementado, opcional | Enlace temporal creado por MCP con imágenes, métricas, decisiones, recálculo, aceptación y descarga |
| 4. Incorporación de datasets | aplazado por decisión de producto | El piloto usa solamente el dataset sandbox registrado |
| 5. Informe científico | implementado | ZIP con PDF, HTML, JSON, métodos, parámetros, literatura, decisiones, láminas QC, mapas vigentes, BIDS `dataset_description` y hashes |
| 6. Robustez operativa | implementado para el piloto | Supervisor con exclusión mutua, reinicio, autostart, log local, leases y `get_system_health` |
| 7. Validación interna | implementada para el alcance sandbox | Matriz trazable, pruebas automáticas, prueba MATLAB real del subconjunto y recorrido remoto sandbox |
| 8. Piloto externo | preparado; pendiente de participantes | Protocolo, tareas, métricas y criterios de aceptación para 3–5 investigadores |

## Criterio de salida

Un investigador debe poder completar desde Codex o desde el portal opcional:

1. consultar literatura y confirmar parámetros;
2. ejecutar o abrir el análisis sandbox;
3. revisar cada sujeto y registrar decisiones;
4. recalcular el segundo nivel cuando cambie la muestra;
5. aceptar científicamente la versión vigente;
6. descargar un paquete reproducible;
7. completar el recorrido sin terminal ni edición manual de YAML.

## Guion del piloto externo

Cada sesión dura aproximadamente 45 minutos: introducción breve, elección de
parámetros con evidencia, revisión de tres sujetos, cambio de muestra,
recálculo, decisión científica y descarga. Se registran tiempo por tarea,
errores, preguntas, confianza declarada y cualquier paso que requiera ayuda.

El alta de datasets propios, la instalación institucional del worker y la
composición modular de pipelines permanecen fuera del alcance de este piloto.
La evidencia técnica está registrada en `internal-validation.md` y la ejecución
con investigadores en `external-pilot-protocol.md`.
