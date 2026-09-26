# Censo preliminar paper × componente

Este censo incluye **138 papers**: 45 con estructura verificada contra texto completo y 93 basados en extracciones históricas no verificadas.

Los valores `legacy_extracted` son candidatos para revisión. No deben interpretarse como confirmación de que el componente fue ejecutado ni como recomendación metodológica.

## Componentes candidatos

| Componente | Verificados | Candidatos heredados | Total candidato | % corpus |
| --- | ---: | ---: | ---: | ---: |
| `functional_structural_input` | 43 | 95 | 138 | 100.0% |
| `denoising` | 44 | 90 | 134 | 97.1% |
| `conn_preprocessing` | 35 | 93 | 128 | 92.8% |
| `group_inference` | 44 | 79 | 123 | 89.1% |
| `qc` | 45 | 61 | 106 | 76.8% |
| `seed_to_voxel` | 23 | 24 | 47 | 34.1% |
| `roi_to_roi` | 27 | 0 | 27 | 19.6% |
| `external_preprocessing` | 12 | 7 | 19 | 13.8% |
| `machine_learning` | 1 | 15 | 16 | 11.6% |
| `longitudinal_design` | 3 | 11 | 14 | 10.1% |
| `task_connectivity` | 8 | 3 | 11 | 8.0% |
| `structural_morphometry` | 9 | 0 | 9 | 6.5% |
| `graph_theory` | 6 | 2 | 8 | 5.8% |
| `external_preprocessed_input` | 1 | 6 | 7 | 5.1% |
| `task_activation` | 4 | 0 | 4 | 2.9% |
| `network_to_network` | 3 | 0 | 3 | 2.2% |
| `bids_input` | 0 | 2 | 2 | 1.4% |
| `ica_or_dual_regression` | 2 | 0 | 2 | 1.4% |
| `ppi_or_gppi` | 2 | 0 | 2 | 1.4% |
| `structural_parcellation` | 2 | 0 | 2 | 1.4% |
| `voxel_to_voxel_or_mvpa` | 2 | 0 | 2 | 1.4% |
| `alff_or_falff` | 1 | 0 | 1 | 0.7% |
| `clinical_correlation` | 1 | 0 | 1 | 0.7% |
| `diffusion_connectometry` | 1 | 0 | 1 | 0.7% |
| `dynamic_connectivity` | 1 | 0 | 1 | 0.7% |
| `functional_parcellation` | 1 | 0 | 1 | 0.7% |
| `homotopic_connectivity` | 1 | 0 | 1 | 0.7% |
| `lesion_mapping` | 1 | 0 | 1 | 0.7% |
| `roi_to_voxel` | 1 | 0 | 1 | 0.7% |
| `spm_project_import` | 1 | 0 | 1 | 0.7% |

## Combinaciones preliminares de análisis

| Combinación detectada | Papers |
| --- | ---: |
| `unspecified_analysis` | 41 |
| `seed_to_voxel` | 28 |
| `longitudinal_design` | 10 |
| `machine_learning` | 9 |
| `external_preprocessed_input + external_preprocessing` | 3 |
| `structural_morphometry + seed_to_voxel` | 3 |
| `external_preprocessing + roi_to_roi` | 2 |
| `roi_to_roi` | 2 |
| `structural_morphometry + roi_to_roi` | 2 |
| `seed_to_voxel + machine_learning` | 2 |
| `external_preprocessed_input + external_preprocessing + machine_learning` | 2 |
| `roi_to_roi + network_to_network` | 2 |
| `external_preprocessing + seed_to_voxel + roi_to_roi + graph_theory + task_activation` | 1 |
| `external_preprocessing + seed_to_voxel + roi_to_roi + graph_theory + task_connectivity` | 1 |
| `external_preprocessing + structural_parcellation + roi_to_roi` | 1 |

## Uso correcto

- Usar los conteos para seleccionar la muestra profunda y encontrar huecos de cobertura.
- Recalcular las frecuencias después de cada revisión contra texto completo.
- No usar estos conteos para elegir defaults, afirmar buenas prácticas o comparar validez científica.
- Mantener diseño experimental y familia de análisis como dimensiones separadas en la taxonomía definitiva.
