# Validación interna del piloto sandbox

Esta matriz define qué se prueba, la evidencia esperada y el criterio de salida.
Las decisiones científicas sobre sujetos quedan siempre a cargo de un investigador.

| Caso | Evidencia | Criterio de aprobación | Estado |
|---|---|---|---|
| Ejecución sandbox completa | job remoto, manifiesto y hashes | estado `succeeded`, completitud técnica separada de QC | aprobado |
| QC por sujeto | ART, registration, normalization, segmentation, denoising, tSNR y DVARS | métricas y láminas asociadas al sujeto y a `result_version` | aprobado para ejecuciones nuevas |
| Cambio de muestra | recálculo MATLAB con máscara de sujetos | reutiliza primer nivel, crea salida versionada y no modifica versiones previas | aprobado mediante prueba real local |
| Muestra insuficiente | prueba automática con un sujeto aceptado | bloquea segundo nivel con mensaje explícito | aprobado |
| Exclusión sin motivo | prueba automática del control plane | rechaza la decisión | aprobado |
| Resultado obsoleto | pruebas de versiones | rechaza decisiones sobre `result_version` o `sample_version` anterior | aprobado |
| Caída o reinicio del worker | lease, heartbeat, supervisor y estado persistido | reinicia sin ejecutar dos workers y conserva el job recuperable | aprobado para piloto de una estación |
| Aislamiento entre usuarios | pruebas de ownership | un usuario no puede leer ni alterar proyectos o jobs ajenos | aprobado |
| Paquete reproducible | prueba ZIP | incluye PDF/HTML/JSON, decisiones, evidencia, imágenes/mapas y hashes | aprobado |
| Flujo sin portal | herramientas MCP | literatura, ejecución, QC, recálculo, aceptación y paquete se completan desde Codex | aprobado por interfaz |

## Evidencia ejecutada

- Suite automática completa con `python -m unittest discover -s tests -q`.
- Recálculo MATLAB/CONN real sobre `sub-10159` y `sub-10189`, conservando el
  primer nivel y generando un `SPM.mat` independiente.
- Generación CONN QA real para registration, normalization, segmentation,
  ART y denoising sobre el sandbox.
- Despliegue remoto con PostgreSQL, almacenamiento S3 y worker local supervisado.

## Límites conocidos

- El sandbox contiene tres sujetos y no representa toda la variabilidad de un
  estudio real.
- La incorporación de datasets propios está aplazada.
- La prueba externa requiere decisiones de QC realizadas por los participantes;
  no se simulan como decisiones científicas del sistema.
