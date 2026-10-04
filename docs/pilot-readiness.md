# Hoja de ruta de la beta sandbox

Esta hoja sustituye el plan anterior de once pasos. El portal de revisión y la
validación específica de resiliencia operativa quedan fuera de esta versión.
Las decisiones de calidad se realizan mediante herramientas MCP autenticadas y
las imágenes se consultan mediante URLs firmadas temporales.

| Paso | Estado | Entregable verificable |
|---|---|---|
| 1. Alcance y trazabilidad | completado | Matriz que vincula cada capacidad de la beta con prueba, evidencia y limitación |
| 2. ROI-to-ROI integral | completado | Corrida remota completa, QC por sujeto, segundo nivel y artefactos versionados |
| 3. Matriz estadística | implementado | SBC y ROI-to-ROI con una muestra y dos grupos con covariable |
| 4. Parámetros y literatura | implementado | Siete parámetros obligatorios, evidencia versionada y confirmación del investigador |
| 5. QC y aceptación científica | implementado | Completitud técnica, calidad por sujeto, versión de muestra y decisión científica separadas |
| 6. Auth0 y aislamiento | completado | Identidad por usuario, autorización y ausencia de acceso cruzado entre proyectos |
| 7. Reproducibilidad | implementado | ZIP con PDF, HTML, JSON, métodos, parámetros, literatura, decisiones, láminas QC, mapas y hashes |
| 8. Constructor modular | implementado para el catálogo beta | Grafo tipado, validación de compatibilidad y plan de nodos reproducible |
| 9. Plugin privado | completado localmente | Paquete instalable con MCP remoto y cuatro skills para diseñar, ejecutar, revisar y comparar métodos |
| 10. Liberación beta | completado | Versión identificable, pruebas automáticas, evidencia integral y protocolo para 3–5 investigadores |

## Criterio de salida

Un investigador debe poder completar desde Codex:

1. consultar las capacidades y flujos disponibles;
2. crear un flujo guiado, consultar literatura y confirmar parámetros;
3. ejecutar o abrir el análisis sandbox;
4. revisar cada sujeto y registrar decisiones;
5. recalcular el segundo nivel cuando cambie la muestra;
6. registrar la decisión científica sobre la versión vigente;
7. descargar un paquete reproducible;
8. completar el recorrido sin terminal ni edición manual de YAML.

## Guion del piloto externo

Cada sesión dura aproximadamente 45 minutos: introducción breve, elección de
parámetros con evidencia, revisión de tres sujetos, cambio de muestra,
recálculo, decisión científica y descarga. Se registran tiempo por tarea,
errores, preguntas, confianza declarada y cualquier paso que requiera ayuda.

El alta de datasets propios, la instalación institucional del worker y la
composición libre fuera de plantillas modulares validadas permanecen fuera del alcance de este piloto.
La evidencia técnica está registrada en `internal-validation.md`, la matriz
detallada en `beta-validation-matrix.md` y la ejecución con investigadores en
`external-pilot-protocol.md`.

## Fuera del alcance actual

El alta de datasets propios, el portal web de revisión, las pruebas específicas
de recuperación ante reinicios o cortes de red y la composición completamente
libre fuera de módulos validados se conservan como deuda de producto.
