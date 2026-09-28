# Constructor modular de pipelines

El constructor representa cada análisis como un grafo dirigido de módulos
versionados. La primera versión no permite unir nodos arbitrariamente: ofrece
plantillas completas que el catálogo clasifica como validadas o experimentales
y bloquea cualquier composición alterada.

## Plantillas disponibles

- `rsfmri_seed_to_voxel@1.0.0`: mapas de conectividad de una o más regiones
  contra el cerebro completo.
- `rsfmri_roi_to_roi@1.0.0`: matrices de conectividad entre al menos dos
  regiones incorporadas en CONN.

Ambas comparten inspección BIDS, preprocesamiento MNI, denoising aCompCor y
recolección de QC. Cada una tiene módulos propios de primer y segundo nivel.

## Identidad e invalidación

Cada nodo recibe una identidad calculada a partir de su versión, las decisiones
del proyecto que consume y las identidades de sus dependencias. Esto permite
anticipar el impacto de un cambio:

| Cambio | Primer nodo invalidado |
|---|---|
| Dataset o sujetos | inspección |
| Parámetros de preprocesamiento | preprocesamiento |
| Parámetros de denoising | denoising |
| Regiones seleccionadas | primer nivel |
| Grupos, covariables o contrastes | segundo nivel |

Los nodos anteriores al primer cambio conservan su identidad. En la ejecución
actual, un job idéntico se reutiliza completo y el recálculo de muestra reutiliza
preprocesamiento, denoising y primer nivel. La copia o enlace de derivados
intermedios entre proyectos diferentes todavía no se ejecuta automáticamente.

## Interacción

El investigador puede consultar las plantillas y módulos mediante
`get_pipeline_builder_capabilities`, crear una de ellas con
`compose_pipeline` (manteniendo `start_available_flow` por compatibilidad), inspeccionar el grafo resuelto con
`get_project_pipeline_graph` y anticipar el efecto de cambios mediante
`preview_pipeline_change`. El portal muestra el grafo ejecutado junto con QC y
decisiones científicas.

## Límites deliberados

- No se acepta MATLAB libre.
- No se permiten conexiones de nodos fuera del catálogo.
- Las ROIs externas, los diseños longitudinales y las medidas repetidas siguen
  fuera del contrato.
- El estado experimental o validado se publica por plantilla y módulo.
