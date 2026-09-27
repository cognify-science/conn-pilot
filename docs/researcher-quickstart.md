# Guía rápida para el investigador

El producto puede utilizarse conversando con Codex. No requiere terminal,
rutas locales ni edición manual de archivos de configuración.

## 1. Consultar lo disponible

Pregunte:

> ¿Qué análisis puede ejecutar CONN Pilot ahora y sobre qué datasets?

Codex consultará el estado real del producto y mostrará solamente los flujos
ejecutables, sus diseños, semillas, etapas, salidas y limitaciones.

## 2. Crear el análisis

Seleccione un flujo, un dataset y una o más semillas publicadas. Por ejemplo:

> Quiero crear un análisis resting-state seed-to-voxel de una muestra sobre el
> sandbox, usando las semillas de amígdala izquierda y derecha. Mi pregunta es…

El sistema crea un proyecto asociado a la identidad autenticada del
investigador y devuelve los parámetros metodológicos todavía pendientes.

## 3. Resolver parámetros

Para cada parámetro, Codex presenta opciones observadas en la literatura, su
aplicabilidad y las citas correspondientes. El investigador selecciona el valor
y explica su motivo. La frecuencia de uso en papers nunca se convierte en una
selección automática.

Puede preguntar:

> ¿Qué opciones publicadas hay para el filtro temporal de este proyecto?

> Elijo esta opción por el TR y el objetivo del estudio.

## 4. Ejecutar

Cuando no queden decisiones pendientes, indique:

> Ejecutá el flujo disponible de este proyecto.

El producto valida el contrato y encola el trabajo. Si todavía falta algo,
devuelve el parámetro exacto y la próxima acción. Repetir la orden no duplica el
job vigente.

## 5. Revisar y cerrar

Al finalizar, el investigador puede revisar imágenes y métricas por sujeto,
registrar `accept`, `exclude` o `needs_review`, recalcular el segundo nivel si
cambió la muestra, registrar la decisión científica y exportar el paquete
reproducible. El portal visual es opcional; el recorrido completo también puede
realizarse desde Codex.

## Alcance actual

El flujo guiado disponible es resting-state seed-to-voxel de una muestra sobre
datasets BIDS registrados. El sandbox ofrece semillas de amígdala izquierda y
derecha. La incorporación de datasets propios y la composición libre de nuevos
pipelines permanecen fuera del alcance de este piloto.
