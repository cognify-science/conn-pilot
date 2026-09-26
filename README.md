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
- Servidor MCP local por `stdio` para desarrollo y diagnóstico.
- Plano de control MCP en Railway con PostgreSQL, almacenamiento de artefactos y autenticación.
- Worker en una desktop que conserva las neuroimágenes localmente y reclama trabajos cuando está disponible.

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

El resumen de QC verifica completitud técnica e indexa la evidencia por sujeto.
La ejecución de MATLAB exporta para cada sujeto la captura ART, cantidad y
porcentaje de outliers, máximo de señal global y valores de movimiento. La
revisión remota conserva por separado la completitud técnica, la calidad de
cada sujeto y la aceptación científica del análisis.

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

El proceso no imprime una interfaz: queda esperando mensajes MCP por entrada estándar. `config/mcp-server.example.json` contiene una plantilla portable.

Las variables admitidas son:

- `CONN_PILOT_CATALOG`: catálogo versionado de pipelines.
- `CONN_PILOT_ENVIRONMENT`: configuración local de MATLAB, SPM y CONN.
- `CONN_PILOT_WORK_ROOT`: base SQLite, ejecuciones y resultados.

Este transporte sirve para un cliente que corre en la misma PC. El acceso desde otra computadora requiere la siguiente capa: Streamable HTTP, autenticación y TLS o un túnel privado.

## Arquitectura distribuida

`conn_pilot.control_plane` publica un MCP Streamable HTTP permanentemente disponible. Guarda usuarios, proyectos, cola, leases y eventos en PostgreSQL. Los archivos seleccionados de resultados se guardan en un bucket S3 privado. Las neuroimágenes y sus rutas permanecen en la desktop.

`conn_pilot.distributed_worker` establece únicamente conexiones HTTPS salientes. Publica un inventario sanitizado de datasets, reclama un trabajo mediante un lease, materializa el YAML con rutas locales, ejecuta el motor determinístico y sube manifiestos, QC y resultados finales seleccionados.

La conexión de la desktop puede interrumpirse. MATLAB/CONN continúa localmente y el worker conserva la asociación entre el trabajo remoto y el trabajo local, reintenta la sincronización con espera exponencial y publica el resultado cuando Railway vuelve a estar disponible. Un trabajo remoto que ya haya sido marcado como fallido por una interrupción recuperable puede volver a la cola con `retry_job` sin repetir una ejecución local que siga registrada.

```text
Codex -> MCP/API Railway -> PostgreSQL
                         -> bucket de resultados
                              ^
                              | HTTPS saliente
                         worker desktop -> MATLAB/SPM/CONN -> neuroimágenes locales
```

El contrato está en `contracts/distributed.v1.json`. Los ejemplos de configuración son `config/control-plane.example.env`, `config/worker.example.env` y `config/datasets.example.yaml`.

### Revisión de calidad y aceptación científica

El MCP remoto expone operaciones para revisar y cerrar una versión de resultado:

- `get_qc_summary`: muestra los tres estados independientes y la vigencia del segundo nivel.
- `get_subject_qc`: devuelve métricas ART y enlaces firmados de una hora para las imágenes de cada sujeto.
- `set_subject_qc_decision`: registra `accept`, `exclude` o `needs_review`; toda exclusión exige justificación.
- `record_scientific_decision`: registra `accept`, `reject` o `needs_review` para el análisis completo.
- `request_second_level_recalculation`: congela la muestra aceptada y encola solamente el segundo nivel.
- `get_second_level_recalculation`: informa el estado y la versión del modelo grupal.
- `generate_reproducibility_package`: genera un ZIP versionado con informe PDF/HTML/JSON, métodos, parámetros, literatura, decisiones, láminas QC, mapas vigentes y hashes.
- `create_review_link`: crea un enlace interactivo de una hora para revisar el trabajo en `/review`.

Cada decisión guarda la identidad autenticada, la fecha, `result_version` y,
para la decisión científica, `sample_version`. El historial es append-only. Si
una exclusión cambia la muestra, los resultados de segundo nivel existentes se
marcan como `stale` y se bloquea la aceptación científica hasta ejecutar una
versión calculada con la muestra revisada. Cada ejecución nueva genera además
QA visual nativo de CONN para normalización, registro, segmentación, ART y
denoising, junto con tSNR, DVARS, volúmenes retenidos y rachas de outliers. El contrato está en
`contracts/qc_review.v1.json`.

### Asesor de literatura en el cliente

El plano de control publica evidencia metodológica estructurada mediante MCP y
deja la interpretación a ChatGPT, Codex u otro cliente con IA. Railway no llama
a un proveedor de modelos y no necesita `OPENAI_API_KEY`.

Las herramientas disponibles son:

- `list_guidance_topics`
- `get_parameter_guidance`
- `compare_method_options`
- `get_evidence_record`
- `validate_parameter_choice`
- `record_method_decision`
- `list_method_decisions`
- `list_unresolved_project_parameters`
- `get_project_parameter_guidance`
- `resolve_project_parameter`

Las consultas distinguen observaciones explícitas, inferidas y no reportadas.
Las comparaciones son descriptivas: nunca convierten la frecuencia en un valor
recomendado. Una decisión confirmada por el investigador conserva en PostgreSQL
la versión del corpus, la justificación y una copia exacta de la evidencia
consultada. El contrato está en `contracts/literature_guidance.v1.json`.

El `Parameter Resolver v1` conecta esa evidencia con los siete parámetros
ejecutables iniciales de preprocessing y denoising. Filtra las observaciones
por el contrato de la versión del pipeline y por metadatos del dataset, exige
una coincidencia explícita para la opción elegida y actualiza en una sola
transacción el proyecto y su decisión metodológica. En Railway, un proyecto no
puede enviarse mientras alguno de esos parámetros carezca de confirmación,
evidencia y versión de corpus. El plan de ejecución incluye los parámetros
resueltos y sus identificadores de decisión. El contrato está en
`contracts/parameter_resolver.v1.json`.

El worker se inicia con:

```powershell
.venv\Scripts\python.exe -m conn_pilot.distributed_worker
```

En la desktop Windows, `scripts/run_distributed_worker.ps1` carga la configuración local y mantiene el worker consultando la cola. El script impide instancias duplicadas y reinicia el proceso si termina inesperadamente; un acceso directo en la carpeta de inicio de Windows hace que vuelva a operar después de reiniciar la PC.

`scripts/install_worker_autostart.ps1` instala ese inicio automático y
`scripts/uninstall_worker_autostart.ps1` lo elimina. El supervisor registra
reinicios y fallos en `work/logs/worker-supervisor.log`. La herramienta MCP
`get_system_health` muestra presencia del worker, bucket y colas de ejecución.

Cada investigador conecta Codex usando la URL pública y una credencial propia:

```powershell
codex mcp add conn-pilot --url https://HOST/mcp --bearer-token-env-var CONN_PILOT_TOKEN
```

En Windows también puede usarse `scripts/codex_conn_pilot_headers.ps1` como `http_headers_helper`. El helper obtiene la credencial de `CONN_PILOT_TOKEN` o de un archivo local ignorado por Git, y evita guardar el token dentro de `config.toml`.

### Identidad de investigadores

El plano de control puede validar tokens OAuth breves emitidos por Auth0 además de la credencial administrativa local usada durante la migración. La API de Auth0 debe usar como identificador la URL MCP pública exacta, JWT RFC 9068 firmado con RS256 y el permiso `conn-pilot:use`. En el tenant se habilitan Resource Parameter Compatibility Profile, Client ID Metadata Document (CIMD) Registration y Dynamic Client Registration (DCR) para admitir clientes MCP actuales.

```env
CONN_PILOT_AUTH0_ISSUER=https://your-tenant.us.auth0.com/
CONN_PILOT_AUTH0_AUDIENCE=https://your-service.example/mcp
```

El servidor verifica firma, emisor, audiencia, vencimiento, sujeto y el permiso `conn-pilot:use` contra el JWKS publicado por Auth0. Acepta el permiso tanto en `scope` como en `permissions`, según el perfil de token emitido por Auth0. La primera solicitud válida registra el identificador externo como investigador; una identidad revocada localmente no se reactiva al iniciar sesión otra vez. Los proyectos y trabajos siguen aislados por sujeto autenticado.

Durante el piloto se usa la conexión Passwordless Email de Auth0 con códigos de seis dígitos, altas públicas deshabilitadas y promoción a nivel de dominio para clientes OAuth de terceros. El administrador incorpora cada correo antes de que el investigador conecte su cliente MCP. DCR permite registrar clientes como Codex, ChatGPT o Claude; no habilita por sí mismo una cuenta de investigador. Auth0 puede usar su proveedor de correo incorporado para la prueba inicial; antes de producción debe configurarse un proveedor SMTP propio.

## Alcance inicial

- Investigadores autenticados y datasets registrados en la desktop.
- Proyectos y decisiones versionados.
- Validación explícita de capacidades y parámetros.
- Ejecuciones trazables, con controles de calidad y revisión del investigador.

Las imágenes fuente no se transfieren a Railway. La incorporación de un dataset nuevo requiere registrarlo localmente en la desktop.

## Deuda técnica documentada

- [Contrato modular de flujos y criterios de aceptación](docs/technical-debt.md)
- [Evaluación del sistema de literatura y orientación metodológica](docs/literature-guidance-evaluation.md)
- [Plan de revisión y taxonomía de pipelines](docs/pipeline-literature-review-plan.md)
- [Revisión reproducible: manifiesto, esquema, censo y casos normalizados](knowledge/pipeline_review/README.md)

## Garantías del motor

- Rechaza campos y parámetros desconocidos.
- Aplica rangos y compatibilidades declarados por la versión del pipeline.
- Bloquea decisiones científicas sin confirmación.
- Genera MATLAB sólo desde un proyecto validado.
- Copia las imágenes a un directorio aislado por ejecución antes de invocar CONN, porque el preprocesamiento modifica encabezados y crea derivados junto a las entradas.
- Usa identificadores físicos cortos y determinísticos para evitar el límite efectivo de rutas de MATLAB/SPM en Windows, conservando el nombre científico completo en el proyecto y la base de trabajos.
- Conserva una copia del proyecto y hashes del batch ejecutado.
- Marca una ejecución como exitosa sólo si encuentra el proyecto CONN y los resultados de ambos niveles.

La validez técnica no convierte los resultados del dataset de ejemplo en evidencia científica.
