# Matriz de validación de CONN Pilot 0.1.0-beta.1

La matriz registra el criterio de aceptación, la evidencia y la limitación de
cada capacidad incluida en la beta sandbox. Un resultado técnico satisfactorio
no implica aceptación científica ni confirmación de una hipótesis.

| Paso | Capacidad | Criterio de aceptación | Evidencia | Estado |
|---|---|---|---|---|
| 1 | Alcance trazable | cada capacidad pública tiene una prueba o una corrida registrada | esta matriz, contratos y 89 pruebas automáticas | aprobado |
| 2 | ROI-to-ROI integral | CONN remoto finaliza, genera QC, admite revisión de muestra y paquete reproducible | job `81a1c3c97f42452dbaabf67b7ca7cd4b` y [registro de validación](validation/roi-to-roi-2026-10-03.md) | aprobado |
| 3 | Matriz estadística | SBC y ROI-to-ROI producen planes válidos para una muestra y dos grupos con covariable | pruebas de motor y segundo nivel | aprobado por pruebas |
| 4 | Parámetros y literatura | los siete parámetros tienen valor, evidencia versionada y decisión registrada | pruebas del resolutor y corpus | aprobado por pruebas |
| 5 | QC y aceptación | completitud, calidad por sujeto, vigencia del segundo nivel y decisión científica son estados independientes | dos aceptaciones, una exclusión justificada, bloqueo y recálculo real | aprobado |
| 6 | Auth0 y aislamiento | un sujeto no puede leer ni mutar recursos de otro | pruebas de ownership; endpoint devuelve 401, metadata Auth0 y scope `conn-pilot:use` | aprobado |
| 7 | Reproducibilidad | el ZIP contiene informes, especificación, evidencia, decisiones, imágenes y hashes verificables | ZIP de 36 archivos; hash remoto y descarga local coinciden | aprobado |
| 8 | Constructor modular | rechaza grafos incompatibles y fija un plan reproducible | pruebas de composición y catálogo versionado | aprobado por pruebas |
| 9 | Plugin privado | manifiestos válidos, skills válidas, marketplace instalable y MCP autenticable | esquemas Agent Plugins, cuatro skills y `conn-pilot@conn-pilot-private` instalado en Codex | aprobado localmente |
| 10 | Beta versionada | versión coherente, suite completa aprobada y protocolo externo listo | `0.1.0-beta.1`, suite de 89 pruebas, plugin y protocolo | aprobado |

## Alcance aplazado

- Portal de revisión web.
- Alta de datasets propios.
- Validación deliberada de recuperación ante reinicios y cortes de red.
- Composición libre con módulos fuera del catálogo validado.
- Inferencia científica con potencia adecuada: el dataset sandbox de tres sujetos
  valida el producto y su trazabilidad, no una conclusión neurocientífica.
