# Semilla de revisión de pipelines

Este directorio contiene la primera normalización reproducible del corpus
heredado de CONN. No constituye todavía una revisión científica de los papers.

## Contenido

- `snapshot.yaml`: identificación y conteos del corpus congelado.
- `corpus_manifest.csv`: 138 papers únicos, referencias a archivos y hashes.
- `schemas/pipeline_instance_v1.schema.json`: contrato de una instancia de
  pipeline observada en la literatura.
- `instances/`: instancias normalizadas de todos los papers revisados.
- `curation/pilot_source_reviews.yaml`: verificación estructural contra los
  métodos publicados y decisiones de separación de instancias.
- `component_dictionary.yaml`: componentes observados en los casos revisados.
- `core_taxonomy_v1.yaml`: taxonomía componible derivada del estrato central
  completo; separa dimensiones, componentes, patrones y reglas de evidencia.
- `completed_stratified_review.md`: síntesis de los 45 papers revisados y
  requisitos derivados para el motor flexible y el asistente de literatura.
- `initial_gap_report.md`: cobertura, decisiones de esquema y huecos.
- `paper_component_matrix.csv`: censo conservador de los 138 papers con
  estados de evidencia por componente.
- `component_prevalence.csv` y `preliminary_census_report.md`: conteos
  preliminares separados entre verificados y candidatos heredados.
- `deep_review_queue.csv`: muestra estratificada completa de 45 papers, todos
  con verificación estructural.

La estructura general de los cuarenta y cinco casos fue contrastada con el
texto completo.
Los campos `inferred` todavía requieren revisión parámetro por parámetro antes
de usarse como orientación científica. Una práctica observada tampoco implica
que sea una recomendación metodológica.

## Regeneración

Desde la raíz de `conn-pilot`:

```powershell
python scripts\build_pipeline_review_seed.py `
  --source-root C:\ruta\a\conn-knowledge-builder `
  --output-root knowledge\pipeline_review
```

El generador exige 138 PMIDs únicos y valida los identificadores, capas y
aristas de todas las instancias revisadas.
