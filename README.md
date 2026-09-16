# CONN Pilot

Asistente de IA para diseñar, validar y ejecutar análisis reproducibles con CONN Toolbox.

## Estado

El motor local v0.1 implementa y validó de punta a punta el primer pipeline determinístico:

- resting-state fMRI en BIDS;
- seed-to-voxel;
- una sesión por sujeto;
- una muestra o dos grupos independientes;
- covariables continuas opcionales;
- preprocessing `default_mni`;
- denoising aCompCor;
- modelos de primer y segundo nivel;
- trabajos persistentes y manifiestos de resultados.

La corrida técnica de referencia con tres sujetos terminó correctamente en MATLAB R2023b, SPM25 y CONN 25.b; produjo seis mapas SBC de primer nivel y un modelo SPM de segundo nivel para las dos semillas de amígdala.

El proyecto `conn-automation` sirve como referencia; sus implementaciones y resultados no se consideran automáticamente validados para CONN Pilot.

## Arquitectura

- Núcleo determinístico para configurar, validar y ejecutar análisis.
- Catálogo versionado de familias, pipelines y etapas reutilizables.
- Conocimiento metodológico con fuentes y condiciones de aplicación.
- Servidor MCP local por `stdio`, orientado inicialmente a Claude Science y otros clientes compatibles.
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

## Operaciones para la IA

El módulo `OperationService` expone nueve operaciones con un sobre JSON estable y versionado. El mismo límite de aplicación puede ser usado desde terminal ahora y, más adelante, por un servidor MCP o una API sin duplicar la lógica científica ni la de ejecución.

```powershell
python -m conn_pilot operation list_pipelines
python -m conn_pilot operation inspect_dataset examples/reference_project.local.yaml
python -m conn_pilot operation validate_project examples/reference_project.local.yaml
python -m conn_pilot operation generate_execution_plan examples/reference_project.local.yaml
python -m conn_pilot operation submit_job examples/reference_project.local.yaml
python -m conn_pilot operation get_job_status JOB_ID
python -m conn_pilot operation get_job_logs JOB_ID --stream all --tail 200
python -m conn_pilot operation list_results JOB_ID
python -m conn_pilot operation get_qc_summary JOB_ID
```

`submit_job` guarda el pedido y lanza un proceso local separado, por lo que devuelve el identificador sin esperar a que termine MATLAB. La base SQLite admite una sola ejecución activa para evitar que dos análisis compitan por CPU, memoria y licencias. Las respuestas contienen `schema_version`, `operation`, `ok`, `data`, `errors` y `warnings`. El contrato completo está en `contracts/operations.v1.json`.

El resumen de QC verifica completitud técnica e indexa la evidencia por sujeto. Esta versión deja explícitamente la decisión científica de aceptar o excluir sujetos para revisión humana.

## Servidor MCP local

El servidor MCP usa el SDK oficial Python 2.2.0 y publica las mismas nueve operaciones como herramientas tipadas. No contiene lógica paralela: cada herramienta llama a `OperationService` y devuelve su sobre JSON versionado.

La instalación local queda aislada en `.venv`:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
```

Un cliente MCP debe iniciar este proceso por `stdio`:

```powershell
.venv\Scripts\python.exe -m conn_pilot.mcp_server
```

El proceso no imprime una interfaz: queda esperando mensajes MCP por entrada estándar. `config/mcp-server.example.json` contiene una plantilla portable y `config/claude_desktop.local.json` contiene las rutas absolutas de esta PC; el segundo archivo está excluido de Git.

Las variables admitidas son:

- `CONN_PILOT_CATALOG`: catálogo versionado de pipelines.
- `CONN_PILOT_ENVIRONMENT`: configuración local de MATLAB, SPM y CONN.
- `CONN_PILOT_WORK_ROOT`: base SQLite, ejecuciones y resultados.

Este transporte sirve para un cliente que corre en la misma PC. El acceso desde otra computadora requiere la siguiente capa: Streamable HTTP, autenticación y TLS o un túnel privado.

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
