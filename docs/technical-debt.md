# Deuda técnica y próximos hitos

Este documento registra decisiones deliberadamente postergadas. Una deuda no se
considera resuelta hasta cumplir sus criterios de aceptación.

## TD-001 — Contrato modular de flujos científicos

**Estado:** resuelta en su primera versión operativa (2026-09-27)
**Momento de resolución:** antes de incorporar el segundo pipeline ejecutable  
**Motivo:** `conn_pilot_project_v1` y el pipeline
`rsfmri_seed_to_voxel@1.0.0` describen un flujo completo y fijo. Agregar una
entrada de catálogo por cada combinación completa duplicaría preprocessing,
denoising, QC y reglas de compatibilidad.

### Alcance esperado

- Diseñar `conn_pilot_project_v2` como composición tipada de módulos
  versionados: entrada, preprocessing, denoising, primer nivel, segundo nivel,
  QC y exportación.
- Mantener una matriz explícita de compatibilidades entre módulos.
- Distinguir combinaciones `validated`, `experimental` y `unsupported`.
- Resolver una configuración modular a un plan determinístico antes de generar
  MATLAB.
- Mantener lectura y reproducción de proyectos `v1`; cualquier migración debe
  ser explícita y conservar el original.
- Impedir código MATLAB libre y parámetros fuera del contrato.

### Criterios de aceptación

1. Dos pipelines comparten al menos un módulo sin duplicar su contrato.
2. Una combinación incompatible se bloquea antes de crear un trabajo.
3. El plan resuelto conserva versiones, decisiones y confirmaciones.
4. Un proyecto `v1` existente puede reproducirse sin cambios.
5. Cada combinación ejecutable tiene evidencia de validación identificable.

### Resolución

`conn_pilot_project_v2` incorpora una composición congelada y firmada por el
catálogo. Seed-to-voxel y ROI-to-ROI comparten los módulos de inspección,
preprocesamiento, denoising y QC. El planificador calcula una identidad por nodo
y anticipa qué nodos siguen siendo reutilizables ante un cambio. La ejecución
real reutiliza el trabajo completo cuando el proyecto no cambió y reutiliza el
primer nivel en los recálculos de muestra; la reutilización física de derivados
intermedios entre proyectos distintos queda como optimización posterior.

Las composiciones libres continúan bloqueadas. Solo se aceptan plantillas cuya
combinación y versiones coinciden con el catálogo validado. Los proyectos v1 se
leen y ejecutan sin agregar una composición implícita.

## TD-002 — Orientación metodológica basada en evidencia

**Estado:** MVP operativo; evaluación científica y actualización pendientes  
**Prioridad:** alta antes de presentar opciones como recomendaciones científicas

CONN Pilot carga el corpus inicial, lo consulta por MCP, vincula evidencia
explícita con siete parámetros ejecutables y conserva cada decisión en el
proyecto y PostgreSQL. Todavía debe incorporar evaluación de calidad,
aplicabilidad, contradicciones, actualización del corpus y revisión
metodológica humana. La evaluación y los siguientes hitos están en
[literature-guidance-evaluation.md](literature-guidance-evaluation.md).

### Criterio de seguridad científica

La literatura puede aportar opciones, condiciones de aplicación, precedentes y
advertencias. No debe convertir la frecuencia de uso de un parámetro en una
recomendación universal ni reemplazar la decisión del investigador.

La revisión también se usará para identificar componentes y arquetipos de
pipeline que orienten `conn_pilot_project_v2`. El plan está en
[pipeline-literature-review-plan.md](pipeline-literature-review-plan.md).
