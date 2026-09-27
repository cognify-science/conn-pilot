# Guía rápida para el investigador

El producto puede utilizarse conversando con Codex. No requiere terminal,
rutas locales ni edición manual de archivos de configuración.

## 1. Consultar lo disponible

Pregunte:

> ¿Qué análisis puede ejecutar CONN Pilot ahora y sobre qué datasets?

Codex consultará el estado real del producto y mostrará solamente los flujos
ejecutables, sus diseños, semillas, etapas, salidas y limitaciones.

## 2. Crear el análisis

Busque una o más regiones en el catálogo de semillas y seleccione el diseño.
Puede usar una muestra o dos grupos independientes, con covariables continuas
opcionales y contrastes definidos explícitamente. Por ejemplo:

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

El flujo guiado disponible es resting-state seed-to-voxel sobre datasets BIDS
registrados. Expone las 564 regiones incorporadas en CONN 25.b: 132 del atlas
CONN, 32 regiones de redes y 400 parcelaciones Schaefer. Admite una muestra o
dos grupos independientes, covariables numéricas y múltiples contrastes. El
investigador debe asignar cada sujeto a un grupo, proporcionar un valor por
sujeto para cada covariable y confirmar la hipótesis de cada contraste; el
sistema valida esos datos y no inventa decisiones científicas. La incorporación
de datasets propios y la composición libre de nuevos pipelines permanecen fuera
del alcance de este piloto.
