# Plan de revisión de literatura y taxonomía de pipelines

## Objetivo

Usar la revisión del corpus con dos propósitos separados:

1. construir orientación metodológica trazable para decisiones científicas;
2. identificar los tipos, etapas y variantes de pipelines usados con CONN para
   diseñar un contrato modular más flexible.

La frecuencia de una práctica servirá para estimar demanda y priorizar módulos.
No se interpretará como prueba de que esa práctica sea metodológicamente mejor.

## Alcance inicial

El índice heredado contiene 138 papers únicos. El trabajo se divide en:

- **censo estructural de los 138 papers:** normalización, clasificación y
  extracción de los componentes de pipeline informados;
- **revisión profunda de 45 papers:** lectura metodológica y validación manual
  de afirmaciones, parámetros, etapas y condiciones de aplicación;
- **ampliación por saturación:** agregar papers si los últimos diez revisados
  todavía introducen familias, etapas o incompatibilidades nuevas.

### Muestra profunda inicial

| Estrato | Objetivo aproximado |
| --- | ---: |
| Seed-to-voxel, preprocessing, denoising y comparación grupal | 25 |
| ROI-to-ROI | 5 |
| Graph theory | 5 |
| Task-fMRI/PPI o importación desde SPM | 4 |
| Longitudinal o medidas repetidas | 4 |
| Conectividad dinámica | 1 |
| Extracción de características/ML | 1 |
| **Total** | **45** |

La selección debe priorizar papers metodológicos, descripciones completas,
código disponible y diversidad de adquisición y diseño. No se seleccionará por
resultado positivo o significación estadística.

## Unidad de extracción

Cada paper puede contener una o más configuraciones. La unidad de análisis será
una **instancia de pipeline**, no el paper completo. Cada instancia conservará
su vínculo con la publicación y registrará:

### Contexto

- pregunta y familia de análisis;
- resting-state o task-fMRI;
- población y diseño;
- número de grupos, sesiones y runs;
- TR, duración, resolución y tamaño muestral;
- datos crudos, preprocesados o importados;
- versiones de MATLAB, SPM, CONN y herramientas externas.

### Grafo de ejecución

- etapas ejecutadas y orden;
- entradas y salidas de cada etapa;
- pasos realizados fuera de CONN;
- ramas, repeticiones y análisis de sensibilidad;
- dependencias entre etapas;
- etapa desde la que puede retomarse una ejecución.

### Configuración científica y técnica

- preprocessing y normalización;
- corrección temporal, movimiento y distorsión;
- suavizado;
- confounds, aCompCor, scrubbing, GSR y filtrado;
- definición de ROI, semillas y atlas;
- análisis de primer nivel;
- diseño, covariables y contrastes de segundo nivel;
- correcciones estadísticas;
- QC, reglas de exclusión y outputs.

### Calidad del reporte

Cada campo se marcará como:

- `explicit`: informado directamente;
- `inferred`: inferencia identificada y justificada;
- `not_reported`: ausente;
- `not_applicable`: no corresponde al flujo.

No se completarán datos faltantes con defaults del sistema.

## Taxonomía de componentes

Las instancias se normalizarán en siete capas:

1. **Input adapter:** BIDS crudo, fMRIPrep, derivados propios, proyecto SPM o
   proyecto CONN existente.
2. **Preprocessing:** realineamiento, field maps, slice timing, segmentación,
   normalización y smoothing.
3. **Denoising:** confounds, CompCor, movimiento, scrubbing, filtrado y GSR.
4. **Features o primer nivel:** SBC, ROI-to-ROI, voxel-to-voxel, ICA, ALFF,
   PPI/gPPI, conectividad dinámica o matrices para graph theory.
5. **Segundo nivel:** una muestra, grupos independientes, covariables,
   factorial, longitudinal o medidas repetidas.
6. **QC y decisiones:** métricas, imágenes, exclusión, sensibilidad y revisión.
7. **Resultados y exportación:** mapas, matrices, tablas, modelos, reportes y
   paquetes reproducibles.

Cada componente candidato tendrá:

- identificador y versión;
- parámetros y tipos;
- `requires` y `provides`;
- restricciones y compatibilidades;
- decisiones que requieren confirmación;
- papers donde aparece;
- fuentes metodológicas que justifican su uso;
- estado `observed`, `specified`, `implemented`, `technically_validated` o
  `scientifically_reviewed`.

## Método de análisis

### 1. Congelar el corpus

- Crear un manifiesto con los 138 PMIDs, DOI, archivos y hashes.
- Identificar la ronda histórica de 83 papers.
- Separar fichas automáticas, extracciones profundas y registros auxiliares.

### 2. Normalizar el censo completo

- Unificar nombres, unidades, versiones y variantes ortográficas.
- Deduplicar representaciones del mismo paper.
- Clasificar todas las instancias por familia y estado de entrada.
- Mantener `not_reported` para datos ausentes.

### 3. Revisar profundamente la muestra estratificada

- Verificar cada extracción contra el método publicado y sus suplementos.
- Dividir papers con varios análisis en varias instancias.
- Registrar ubicación del respaldo y condiciones de aplicación.
- Separar “utilizado”, “evaluado” y “recomendado”.

### 4. Construir la matriz paper × componente

La matriz permitirá calcular:

- prevalencia de familias y etapas;
- combinaciones frecuentes;
- componentes reutilizados entre familias;
- variantes incompatibles;
- parámetros habitualmente omitidos;
- dependencia de herramientas externas;
- cobertura potencial de cada módulo nuevo.

### 5. Derivar arquetipos

Agrupar instancias por similitud estructural y revisar manualmente los grupos.
Ejemplos esperados, sujetos a la evidencia:

- BIDS crudo → preprocessing CONN → aCompCor → seed-to-voxel;
- fMRIPrep → importación de confounds → ROI-to-ROI;
- resting-state longitudinal → SBC/ROI → modelo de medidas repetidas;
- task-fMRI/SPM → importación → PPI/gPPI;
- ROI-to-ROI → matriz → graph theory;
- denoising → ventanas temporales → conectividad dinámica.

Un arquetipo no se vuelve ejecutable por aparecer en la literatura. Primero se
convierte en especificación, luego en implementación y finalmente en flujo
validado.

### 6. Priorizar el roadmap

Cada arquetipo y componente se puntuará por separado en:

- frecuencia en el corpus;
- reutilización entre pipelines;
- demanda científica esperada;
- claridad metodológica;
- disponibilidad de datos de referencia;
- dificultad de implementación;
- costo de validación;
- riesgo científico y de privacidad.

La prioridad de producto combinará cobertura, reutilización y viabilidad. La
frecuencia no determinará defaults ni validez científica.

## Entregables

1. Manifiesto reproducible del corpus.
2. Esquema `pipeline_instance_v1` para extracción.
3. Registro versionado de afirmaciones y evidencia.
4. Diccionario de componentes y parámetros normalizados.
5. Matriz paper × componente.
6. Catálogo de arquetipos con prevalencia y contexto.
7. Matriz de compatibilidades e incompatibilidades.
8. Mapa de cobertura del motor actual.
9. Propuesta de `conn_pilot_project_v2` modular.
10. Roadmap priorizado de implementación y validación.

## Criterios de finalización

La revisión estará lista para orientar el nuevo esquema cuando:

1. los 138 papers estén deduplicados y clasificados;
2. al menos 45 tengan revisión profunda y trazable;
3. al menos el 95 % de las instancias pueda asignarse a un arquetipo o quedar
   explícitamente como `other`;
4. diez revisiones profundas consecutivas no introduzcan una capa o familia
   nueva, o se documente por qué no se alcanzó saturación;
5. cada componente propuesto tenga precedentes identificados y condiciones de
   uso;
6. se distingan prevalencia, soporte metodológico y validación interna;
7. el contrato modular reproduzca el pipeline actual sin pérdida;
8. al menos tres arquetipos adicionales puedan expresarse sin duplicar
   definiciones de etapas.

## Orden de ejecución recomendado

1. Congelar y sanear el corpus.
2. Diseñar `pipeline_instance_v1` y probarlo con los ocho casos profundos. **Completado.**
3. Revisar los 25 papers del flujo actual. **Completado.**
4. Revisar los 20 papers estratificados de otras familias. **Completado.**
5. Construir la matriz y los arquetipos. **Completado en su versión estructural.**
6. Diseñar el contrato modular v2 a partir de los resultados. **Siguiente etapa.**
7. Elegir el segundo pipeline por cobertura y capacidad de validación.
8. Implementar y validar ese segundo pipeline como prueba del esquema.

## Estado de ejecución

La primera semilla se generó el 2026-09-22 en
`knowledge/pipeline_review/`. Incluye el manifiesto de 138 papers, hashes de
los archivos disponibles, el esquema `pipeline_instance_v1`, los casos
normalizados, un diccionario inicial de componentes y el informe de huecos.

La revisión mostró que se necesita una octava capa, `downstream_analysis`, para
representar machine learning, correlaciones clínicas y otros análisis externos
sin mezclarlos con segundo nivel ni con exportación. Las cuarenta y cinco
estructuras de la muestra estratificada fueron contrastadas con los métodos
publicados y sus decisiones de ramificación quedaron registradas. La evaluación
científica y la verificación parámetro por parámetro continúan pendientes.

El censo preliminar de los 138 papers y la cola estratificada de 45 casos
también están generados. El censo distingue `source_verified`,
`legacy_extracted` y `not_detected`; los conteos heredados sirven para priorizar
revisión y no representan prevalencias confirmadas.
