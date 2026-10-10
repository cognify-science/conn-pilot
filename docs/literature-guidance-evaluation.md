# Evaluación de orientación metodológica y literatura

Este documento conserva el diagnóstico y plan de desarrollo de la primera capa
de literatura. El estado científico actual, los límites y el protocolo de
comparación están en [gobierno de evidencia](science/evidence-governance.md),
[evaluación del selector](science/parameter-selector-evaluation.md) y
[validación de benchmarks](science/benchmark-validation-2026-10.md).

## Conclusión

La primera capa operativa ya consulta el corpus versionado mediante MCP. Railway
recupera observaciones, compara valores reportados, valida identificadores de
evidencia y conserva las decisiones confirmadas. La interpretación se realiza
con el modelo del cliente, sin una API de IA dentro del servidor.

`Parameter Resolver v1` ya conecta esa capa con siete parámetros ejecutables
del pipeline inicial. Normaliza valores publicados, descarta opciones que el
contrato o el TR del dataset no admiten, exige coincidencia explícita de la
evidencia citada y bloquea el envío remoto hasta que el investigador confirme
cada decisión. La evaluación de calidad y aplicabilidad científica sigue
pendiente.

Antes de presentar recomendaciones como basadas en evidencia se necesita una
capa de conocimiento versionada, consultable, trazable y revisada por personas
con competencia metodológica.

## Qué está implementado en CONN Pilot

### Artefactos existentes

- `knowledge/rsfmri_seed_to_voxel/1.0.0.yaml` contiene tres principios,
  parámetros de referencia para el piloto y dos enlaces a documentación oficial
  de CONN.
- El contrato del proyecto exige `source`, `rationale` y
  `confirmed_by_investigator` para los parámetros.
- El catálogo restringe valores y combinaciones que el generador sabe ejecutar.
- Las decisiones científicas principales requieren confirmación explícita.

### Implementado en el MVP de orientación

- Cargador determinístico de las 45 instancias con verificación estructural.
- Índice por componente, parámetro y contexto del estudio.
- Herramientas MCP para listar temas, recuperar evidencia, comparar opciones y
  consultar un paper revisado.
- Validación de pertenencia y coincidencia explícita de la evidencia citada.
- Persistencia por proyecto de la decisión, justificación, versión del corpus y
  snapshot de evidencia.
- Separación explícita entre valor reportado y validez científica.
- Resolución transaccional de siete parámetros de preprocessing y denoising.
- Validación de tipo, rango, implementación y límite de Nyquist antes de guardar.
- Bloqueo del envío remoto ante decisiones ejecutables sin resolver.
- Inclusión de parámetros resueltos y decisiones en el plan de ejecución.

### Lo que todavía no existe

- Evaluación de calidad, aplicabilidad, contradicciones o incertidumbre.
- Flujo de actualización y revisión de literatura.
- Pruebas que detecten recomendaciones sin respaldo o fuera de contexto.
- Normalización semántica completa de parámetros equivalentes expresados con
  formatos diferentes.
- Cobertura de texto completo para los 93 registros que permanecen como
  extracciones heredadas.
- Recomendaciones científicas ponderadas por calidad y aplicabilidad; la versión
  actual solo presenta opciones compatibles y su frecuencia descriptiva.

En consecuencia, el YAML actual funciona como nota metodológica del pipeline de
referencia, no como sistema de soporte bibliográfico.

## Material recuperable del prototipo anterior

El proyecto `conn-automation` contiene un `knowledge_pack` generado por
`conn-knowledge-builder` con:

- 287 registros de índice que representan 138 PMIDs únicos; el índice conserva
  dos representaciones por paper y agrega políticas, esquemas y plantillas;
- un reporte agregado sobre esos 138 papers;
- un resumen anterior que menciona 83 papers Open Access;
- ocho extracciones profundas;
- plantillas para seed-to-voxel, ROI-to-ROI, graph theory, importación de task
  fMRI y extracción de características para ML;
- un esquema de extracción y políticas preliminares de parámetros y análisis de
  sensibilidad.

Este material es útil como inventario de migración, pero no debe entrar al
producto sin auditoría. Sus documentos declaran que las fichas automáticas son
evidencia preliminar. El número 83 corresponde a una ronda histórica Open
Access; 138 es el total de papers únicos del índice actual y 287 es el total de
registros, no de publicaciones. Falta identificar formalmente las versiones y
reglas de inclusión de cada ronda.

El reporte de frecuencia identifica, por ejemplo, cuántos papers informan 6 u
8 mm de suavizado o determinados filtros temporales. Esa información describe
prácticas publicadas. No establece eficacia, validez ni adecuación a una nueva
adquisición, población o hipótesis. También está afectada por parámetros no
reportados, versiones heterogéneas de CONN/SPM y sesgo de publicación.

## Separación necesaria de fuentes

El sistema debe distinguir el papel de cada clase de evidencia:

1. **Documentación oficial de CONN/SPM:** comportamiento del software,
   parámetros admitidos y semántica de las operaciones.
2. **Papers metodológicos, comparaciones y consensos:** consecuencias, límites
   y criterios para elegir métodos.
3. **Revisiones sistemáticas:** estado de la evidencia y desacuerdos conocidos.
4. **Papers de aplicación:** precedentes en poblaciones y diseños similares;
   sirven como ejemplos, no como validación automática de un default.
5. **Validaciones internas:** combinaciones que CONN Pilot ha reproducido
   técnicamente en entornos conocidos.

La compatibilidad técnica y la justificación científica deben permanecer como
dos evaluaciones separadas.

## Registro mínimo de evidencia

Cada afirmación reutilizable debería ser un registro estructurado con:

- identificador y versión;
- PMID, DOI o URL oficial;
- tipo de fuente y estado de revisión;
- afirmación concreta que la fuente respalda;
- parámetro o decisión relacionada;
- condiciones de aplicación: modalidad, estado de los datos, TR, duración,
  población, sesiones, diseño y familia de análisis;
- valor utilizado en el paper, si fue informado explícitamente;
- distinción entre `explicit`, `inferred` y `not_reported`;
- limitaciones, alternativas y evidencia contradictoria;
- fecha y responsable de la revisión;
- ubicación verificable dentro de la fuente;
- nivel de confianza y fecha de próxima revisión.

Una cita bibliográfica sin una afirmación y condiciones asociadas no es
suficiente.

## Flujo de recomendación propuesto

1. Recoger la pregunta científica, adquisición, estado de preprocessing,
   población, sesiones y diseño.
2. Determinar qué decisiones son necesarias para un pipeline soportado.
3. Consultar registros revisados por decisión y condiciones de aplicabilidad.
4. Presentar opciones con beneficios, limitaciones, incertidumbre y fuentes.
5. Filtrar cualquier opción que el motor no implemente o no haya validado.
6. Solicitar confirmación de las decisiones científicas requeridas.
7. Guardar en el proyecto los identificadores y versiones exactas de evidencia
   mostradas al investigador.
8. Conservar la recomendación y su contexto aunque el corpus cambie después.

La recomendación debe poder responder “por qué esta opción para este estudio” y
“qué alternativas razonables existen”.

## Interfaz implementada

La primera versión expone estas herramientas MCP de solo lectura:

- `list_guidance_topics`
- `get_parameter_guidance`
- `compare_method_options`
- `get_evidence_record`

También expone `validate_parameter_choice` para comprobar la relación entre una
elección y sus registros citados.

La persistencia de una elección es una operación separada:

- `record_method_decision`

La unión con el proyecto ejecutable agrega:

- `list_unresolved_project_parameters`
- `get_project_parameter_guidance`
- `resolve_project_parameter`

`get_parameter_guidance` debería recibir el contexto del estudio y devolver
opciones estructuradas. No debería devolver un único valor presentado como
óptimo.

## Estrategia de actualización

La recomendación en tiempo de ejecución debe usar un corpus curado y congelado.
Una búsqueda web en vivo puede descubrir candidatos, pero no debe convertir un
paper recién encontrado en una recomendación ejecutable.

El ciclo de actualización recomendado es:

1. descubrir fuentes nuevas;
2. deduplicar y clasificar;
3. extraer afirmaciones con trazabilidad;
4. revisar manualmente los registros que afecten decisiones ejecutables;
5. validar el corpus y sus pruebas;
6. publicar una versión inmutable;
7. auditar qué proyectos usaron cada versión.

## Plan de implementación

### Fase 1 — Auditoría y migración

- Congelar y calcular hashes del `knowledge_pack` anterior.
- Documentar la ronda histórica de 83 papers y verificar la correspondencia
  entre los 287 registros y los 138 PMIDs únicos.
- Auditar primero las ocho extracciones profundas.
- Revisar smoothing, outliers, aCompCor, filtro temporal, GSR, semillas,
  contrastes y corrección por comparaciones múltiples.
- Migrar solo afirmaciones con respaldo verificable y aplicabilidad explícita.

### Fase 2 — Núcleo de conocimiento — completada para el corpus inicial

- Definir el esquema de evidencia y validarlo estrictamente.
- Implementar un índice determinístico por tema y condiciones.
- Añadir las cuatro herramientas MCP de consulta.
- Versionar el corpus y registrar su versión en cada proyecto.

### Fase 3 — Integración científica — integración ejecutable inicial completada

- Presentar comparaciones de opciones durante el diseño del proyecto.
- Guardar decisiones, alternativas y evidencia consultada.
- Bloquear afirmaciones sin fuente o fuera de alcance.
- Probar casos con evidencia incompleta, conflictiva y no aplicable.

La presentación de opciones, la persistencia y el bloqueo técnico están
implementados. Restan la evaluación metodológica humana, el tratamiento formal
de contradicciones y las pruebas científicas de aplicabilidad.

## Criterios de aceptación

La deuda puede considerarse resuelta para un parámetro cuando:

1. toda recomendación cita registros existentes y versionados;
2. cada registro identifica la afirmación respaldada y su aplicabilidad;
3. el sistema distingue documentación, método, revisión y precedente;
4. evidencia conflictiva o insuficiente se muestra explícitamente;
5. el proyecto conserva un snapshot de las fuentes consultadas;
6. el motor nunca ejecuta una opción solo porque aparece en la literatura;
7. una revisión metodológica humana aprueba los registros que influyen en una
   ejecución soportada.
