# CONN Pilot

Asistente de IA para diseñar, validar y ejecutar análisis reproducibles con CONN Toolbox.

## Estado

Proyecto nuevo en fase de diseño. Todavía no hay pipelines implementados ni validados para ejecución.

El proyecto `conn-automation` sirve como referencia; sus implementaciones y resultados no se consideran automáticamente validados para CONN Pilot.

## Arquitectura propuesta

- Núcleo determinístico para configurar, validar y ejecutar análisis.
- Catálogo versionado de familias, pipelines y etapas reutilizables.
- Conocimiento metodológico con fuentes y condiciones de aplicación.
- Integración mediante MCP y una skill, inicialmente orientada a Claude Science.
- Piloto con servicio remoto de coordinación y ejecutor en una desktop.

## Primer entregable

Definir conjuntamente una primera porción del catálogo y su fundamento metodológico. El pipeline candidato es resting-state seed-to-voxel para comparación entre dos grupos; el alcance, parámetros y criterios de QC deben especificarse antes de implementarlo.

## Alcance inicial

- Investigadores invitados y datos precargados.
- Proyectos y decisiones versionados.
- Validación explícita de capacidades y parámetros.
- Ejecuciones trazables, con controles de calidad y revisión del investigador.

La transferencia remota y el ciclo de vida completo de datasets propios quedan para una etapa posterior.
