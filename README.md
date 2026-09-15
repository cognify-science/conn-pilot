# CONN Pilot

Asistente de IA para diseñar, validar y ejecutar análisis reproducibles con CONN Toolbox.

## Estado

El motor local v0.1 implementa el primer pipeline determinístico:

- resting-state fMRI en BIDS;
- seed-to-voxel;
- una sesión por sujeto;
- una muestra o dos grupos independientes;
- covariables continuas opcionales;
- preprocessing `default_mni`;
- denoising aCompCor;
- modelos de primer y segundo nivel;
- trabajos persistentes y manifiestos de resultados.

El proyecto `conn-automation` sirve como referencia; sus implementaciones y resultados no se consideran automáticamente validados para CONN Pilot.

## Arquitectura propuesta

- Núcleo determinístico para configurar, validar y ejecutar análisis.
- Catálogo versionado de familias, pipelines y etapas reutilizables.
- Conocimiento metodológico con fuentes y condiciones de aplicación.
- Integración mediante MCP y una skill, inicialmente orientada a Claude Science.
- Piloto con servicio remoto de coordinación y ejecutor en una desktop.

## Uso local

Los comandos pueden ejecutarse sin instalar el paquete:

```powershell
$env:PYTHONPATH = "src"
python -m conn_pilot catalog validate
python -m conn_pilot environment --probe-matlab
python -m conn_pilot validate examples/reference_project.local.yaml --check-paths
python -m conn_pilot generate examples/reference_project.local.yaml --output-dir work/dry-run --check-paths
python -m conn_pilot run examples/reference_project.local.yaml
python -m conn_pilot jobs list
```

`examples/reference_project.local.yaml` y `config/environment.local.yaml` contienen rutas de esta PC y están excluidos de Git.

## Alcance inicial

- Investigadores invitados y datos precargados.
- Proyectos y decisiones versionados.
- Validación explícita de capacidades y parámetros.
- Ejecuciones trazables, con controles de calidad y revisión del investigador.

La transferencia remota y el ciclo de vida completo de datasets propios quedan para una etapa posterior.

## Garantías del motor

- Rechaza campos y parámetros desconocidos.
- Aplica rangos y compatibilidades declarados por la versión del pipeline.
- Bloquea decisiones científicas sin confirmación.
- Genera MATLAB sólo desde un proyecto validado.
- Copia las imágenes a un directorio aislado por ejecución antes de invocar CONN, porque el preprocesamiento modifica encabezados y crea derivados junto a las entradas.
- Conserva una copia del proyecto y hashes del batch ejecutado.
- Marca una ejecución como exitosa sólo si encuentra el proyecto CONN y los resultados de ambos niveles.

La validez técnica no convierte los resultados del dataset de ejemplo en evidencia científica.
