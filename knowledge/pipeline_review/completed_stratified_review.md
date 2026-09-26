# Resultados de la revisión estratificada

## Alcance completado

La muestra definida para revisión profunda quedó completa: **45 de 45 papers**
fueron contrastados con sus métodos publicados. La selección cubre el flujo
central y las familias que introducen variaciones relevantes para un motor de
pipelines componible.

| Estrato | Papers revisados | Pendientes |
| --- | ---: | ---: |
| Flujo central, seeds, preprocessing e inferencia grupal | 25 | 0 |
| ROI-to-ROI | 5 | 0 |
| Graph theory | 5 | 0 |
| Task fMRI | 4 | 0 |
| Longitudinal | 4 | 0 |
| Conectividad dinámica | 1 | 0 |
| Machine learning | 1 | 0 |
| **Total** | **45** | **0** |

Esta revisión verifica la **estructura declarada** de cada pipeline. No convierte
la frecuencia de una práctica en recomendación científica ni sustituye la
evaluación de calidad metodológica.

## Qué mostró la literatura

1. **El pipeline no es una secuencia única.** ROI-to-ROI, seed-to-voxel,
   graph theory, análisis estructural, dinámica y machine learning forman ramas
   paralelas o derivadas. Tres papers de la muestra requieren dos o tres
   instancias provisionales para representar sus análisis sin mezclarlos.
2. **El dueño del preprocessing cambia.** Se observaron flujos nativos de CONN,
   preprocessing externo en SPM, FSL o fMRIPrep, e integraciones híbridas. El
   importador debe conservar software, versión, transformaciones y procedencia.
3. **El origen de seeds y ROIs es parte del método.** Hay regiones definidas por
   atlas o coordenadas, parcellaciones estructurales o funcionales y resultados
   previos del mismo estudio. Las regiones derivadas necesitan una arista
   explícita, un artefacto congelado y control de circularidad.
4. **Task connectivity no equivale siempre a PPI.** La muestra contiene PPI,
   correlación ponderada por HRF y análisis de conectividad por condición. El
   contrato debe exigir modelo, condiciones, regresor psicológico y política de
   filtrado temporal.
5. **Graph theory necesita su propio contrato.** Umbral de aristas, política de
   signos, matriz ponderada o binaria, conjunto de métricas y sensibilidad al
   umbral cambian la interpretación y no pueden quedar escondidos en un nodo
   genérico.
6. **La conectividad dinámica agrega estado y temporalidad.** El caso revisado
   exige ancho de ventana, taper, paso, estimador, selección del número de
   estados, métricas temporales y análisis de sensibilidad.
7. **Longitudinal es una dimensión del diseño.** Debe representar emparejamiento
   por sujeto, sesiones, intervalos, datos faltantes y contrastes repetidos; no
   basta con etiquetar el paper como pre/post.
8. **Parte del análisis ocurre fuera de CONN.** Estadística clínica, graph
   processing, morfometría, ICA dinámica y machine learning pueden consumir
   artefactos de CONN o producir entradas para una rama posterior.

## Correcciones relevantes al censo heredado

La lectura de métodos también mostró que las etiquetas históricas no deben
usarse como verdad de ejecución. Entre las correcciones verificadas:

- un paper históricamente marcado como task fMRI era un análisis resting-state
  de una matriz AAL de 90 por 90 regiones;
- un caso etiquetado como longitudinal era un análisis transversal
  seed-to-voxel con seeds derivados de tractografía previa;
- algunos flujos etiquetados como graph theory eran conectividad ROI-to-ROI o
  network-to-network sin métricas de grafo;
- algunos flujos task usaban conectividad ponderada por HRF y no PPI;
- la conectividad dinámica revisada se ejecutaba fuera de CONN después de la
  preparación de series temporales.

Por eso la matriz conserva por separado la familia histórica, la familia
normalizada y el estado de evidencia de cada componente.

## Requisitos derivados para el motor flexible

El motor v2 debería representar un **grafo dirigido de componentes tipados**.
Cada componente necesita entradas y salidas declaradas, parámetros con estado
de evidencia, entorno de software, reglas de validación, hooks de QC y
procedencia. Las aristas deben distinguir flujo de datos, derivación de una
región, observación de QC y decisiones que habilitan la ejecución.

La interfaz para el investigador puede ofrecer plantillas reproducibles para
los patrones observados, pero debe permitir agregar, eliminar o ramificar
componentes. Antes de ejecutar, el sistema debe validar compatibilidad de
artefactos, parámetros obligatorios y dependencias entre resultados y regiones.

Para aconsejar parámetros a partir de literatura, la base debe separar:

- lo reportado por cada paper;
- lo omitido o ambiguo;
- la evaluación de calidad y aplicabilidad;
- la recomendación final para el experimento concreto y su justificación.

Esta separación evita presentar una práctica frecuente como un valor por
defecto científicamente recomendado.

## Estado del corpus completo

El censo contiene **138 papers**. Los 45 de la muestra estratificada tienen
verificación estructural; los otros **93** conservan extracción heredada sin
verificación contra texto completo. Sus conteos sirven para priorizar la próxima
revisión y no deben interpretarse como prevalencias confirmadas.

La siguiente etapa es traducir la taxonomía verificada al contrato modular v2 y
realizar la evaluación científica de parámetros, calidad y aplicabilidad de la
evidencia para el asistente de literatura.
