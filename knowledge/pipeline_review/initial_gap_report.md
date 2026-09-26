# Informe inicial de cobertura y huecos

Generado el 2026-09-24 a partir del corpus heredado congelado.

## Verificaciones del corpus

- Papers únicos: **138**.
- Registros de las rondas históricas 1–4: **83**.
- Instancias con verificación estructural: **45**.
- Cada archivo fuente disponible quedó identificado mediante SHA-256.

## Familias del censo completo

| Familia | Papers | Casos piloto |
| --- | ---: | ---: |
| `clinical_group_comparison` | 36 | 1 |
| `rsfmri_seed_to_voxel` | 35 | 7 |
| `unclear` | 20 | 0 |
| `machine_learning_features` | 16 | 1 |
| `longitudinal_pre_post` | 14 | 3 |
| `rsfmri_graph_theory` | 6 | 4 |
| `rsfmri_roi_to_roi` | 5 | 6 |
| `task_fmri_connectivity` | 4 | 7 |
| `dynamic_functional_connectivity` | 1 | 1 |
| `rsfmri_qc_preprocessing_denoising` | 1 | 1 |

## Cobertura estructural de la muestra revisada

| Capa | Nodos observados |
| --- | ---: |
| `input_adapter` | 46 |
| `preprocessing` | 45 |
| `denoising` | 44 |
| `first_level_features` | 87 |
| `second_level_inference` | 44 |
| `qc_decision` | 47 |
| `downstream_analysis` | 2 |
| `output_export` | 45 |

## Hallazgos para el contrato flexible

1. El corpus heredado usa dos formas incompatibles de extracción; el nuevo esquema debe ser único y versionado.
2. Los pipelines necesitan un grafo: hay ramas ROI-to-ROI, seed-to-voxel y graph theory que comparten preprocessing y denoising.
3. La entrada debe aceptar datos crudos, derivados de fMRIPrep y proyectos SPM importados.
4. QC es transversal y observa varias etapas; no debe modelarse solamente como el último paso lineal.
5. Machine learning y correlaciones clínicas requieren una capa posterior al análisis CONN.
6. Una publicación puede contener varias instancias. La verificación estructural identificó 3 papers con más de una rama provisional.

## Cobertura y trabajo pendiente

- La muestra estratificada quedó completa: 45 de 45 papers tienen verificación estructural contra texto completo.
- La muestra incluye conectividad dinámica, PPI, task connectivity, análisis longitudinal, graph theory, ROI-to-ROI y machine learning.
- Los parámetros marcados como `inferred` en las extracciones históricas deben contrastarse con texto completo y suplementos.
- Las familias `clinical_group_comparison` y `unclear` mezclan estructura del pipeline con diseño científico y deberán reclasificarse en dimensiones separadas.
- El censo comprende 138 papers; 93 registros fuera de la muestra estratificada siguen sin verificación contra texto completo y sus conteos son candidatos, no prevalencias confirmadas.
- La evaluación de calidad metodológica y la traducción de parámetros observados en recomendaciones científicas siguen siendo una etapa separada.

## Decisión de esquema

El piloto amplía las siete capas del plan con `downstream_analysis`. Esta capa evita mezclar ML, correlaciones clínicas y otros análisis externos con inferencia grupal o exportación.
