# Reglas de capas del proyecto

## Objetivo

Definir responsabilidades claras por capa para evitar que nuevas funcionalidades aumenten el acoplamiento o mezclen reglas de negocio con detalles web, persistencia o presentacion.

Estas reglas aplican a las apps actuales del proyecto: `accounts`, `catalogos`, `inventarios`, `ventas`, `cartera`, `costos`, `cotizaciones`, `notificaciones` e `integraciones_whatsapp`.

## Regla principal

Cada archivo debe tener una razon de cambio dominante. Si un cambio de negocio obliga a modificar vistas, modelos, formularios y servicios a la vez sin necesidad estructural, probablemente la responsabilidad esta mal ubicada.

## `views`

Responsabilidad permitida:

- Recibir `request`.
- Construir formularios o formsets.
- Leer parametros HTTP.
- Llamar selectors para datos de lectura.
- Llamar services o use cases para acciones.
- Traducir errores controlados a `messages`.
- Renderizar templates o redireccionar.

Responsabilidad no permitida:

- Calcular reglas de negocio complejas.
- Crear movimientos de inventario directamente.
- Registrar pagos directamente.
- Calcular credito, comisiones o precios minimos.
- Actualizar muchos modelos como parte de un caso de uso.
- Contener parsing complejo de payloads.

## `forms`

Responsabilidad permitida:

- Validar formato de captura.
- Validar campos requeridos.
- Normalizar valores simples.
- Preparar `cleaned_data`.
- Validar consistencia local del formulario.

Responsabilidad no permitida:

- Ejecutar movimientos de stock.
- Crear pagos o aplicaciones.
- Enviar notificaciones.
- Resolver reglas de credito o autorizaciones.
- Crear objetos relacionados complejos salvo que sea un formulario acoplado por diseno a un modelo simple.

## `models`

Responsabilidad permitida:

- Definir campos y relaciones.
- Definir choices.
- Definir constraints e indices.
- Validar invariantes estructurales con `clean()`.
- Propiedades simples derivadas del propio modelo.
- Normalizaciones minimas necesarias antes de guardar.

Responsabilidad no permitida:

- Ejecutar casos de uso.
- Llamar servicios de otros dominios.
- Crear movimientos relacionados complejos.
- Enviar correos o notificaciones.
- Calcular reglas comerciales cambiantes.
- Consultar otros dominios para tomar decisiones de flujo.

## `selectors`

Responsabilidad permitida:

- Consultas de lectura.
- QuerySets reutilizables.
- Agregaciones.
- Preparacion de contexto de solo lectura para templates.
- Optimizacion de consultas con `select_related` y `prefetch_related`.

Responsabilidad no permitida:

- Crear, actualizar o eliminar registros.
- Ejecutar transacciones de negocio.
- Enviar mensajes o notificaciones.
- Modificar estado de modelos.

Regla: si una funcion cambia datos, no pertenece a `selectors`.

## `services`

Responsabilidad permitida:

- Reglas de negocio.
- Casos de uso.
- Mutaciones de estado.
- Transacciones.
- Coordinacion entre modelos de una misma regla.
- Validaciones de negocio.
- Integracion interna entre dominios mediante servicios o puertos.

Responsabilidad no permitida:

- Renderizar templates.
- Depender directamente de `request` si puede recibir un contexto mas pequeno.
- Mezclar varios casos de uso sin una razon clara.
- Exponer metodos privados para que otros servicios los reutilicen.

Regla: un servicio debe poder explicarse con una frase corta. Si necesita una lista larga de verbos, debe dividirse.

## `use_cases`

Cuando un flujo tiene varias operaciones coordinadas, debe preferirse un caso de uso explicito.

Responsabilidad permitida:

- Orquestar servicios pequenos.
- Controlar la transaccion principal.
- Recibir DTOs o datos ya validados.
- Devolver un resultado estructurado.

Responsabilidad no permitida:

- Hacer parsing HTTP.
- Renderizar respuestas.
- Contener detalles de presentacion.

## `templates`

Responsabilidad permitida:

- Presentar datos.
- Condicionales simples de UI.
- Iterar colecciones preparadas.
- Incluir parciales.

Responsabilidad no permitida:

- Calcular reglas de negocio.
- Inferir estados complejos.
- Duplicar logica de servicios.
- Depender de estructuras dificiles de probar.

## Dependencias recomendadas

Flujo normal:

```text
views -> forms
views -> selectors
views -> use_cases/services
use_cases -> services
services -> models
services -> selectors
selectors -> models
templates <- views
```

Flujo a evitar:

```text
models -> services de otros dominios
selectors -> services mutables
templates -> reglas de negocio
views -> mutaciones complejas de multiples modelos
services -> request completo
servicio A -> metodo privado de servicio B
```

## Dependencias entre apps

Las dependencias directas entre apps deben ser intencionales.

Permitido:

- `ventas` puede hablar con inventario para afectar stock.
- `cartera` puede leer notas de venta para calcular saldos.
- `costos` puede leer ventas e inventarios para calcular resultados.
- `notificaciones` puede leer dominios para reportes.

Debe aislarse con servicios o puertos cuando:

- La regla pueda cambiar por negocio.
- La dependencia provoque ciclos.
- El servicio necesite ser probado sin cargar todo el dominio.
- La app receptora exponga detalles internos del modelo.

## Regla para metodos privados

Un metodo privado (`_nombre`) solo puede usarse dentro de su propia clase o modulo. Si otro servicio necesita esa conducta, debe extraerse a una funcion publica, un servicio propio, un use case o un adaptador.

## Regla para transacciones

Los cambios que afecten varios modelos deben estar en servicios o use cases, no en vistas.

La transaccion principal debe vivir en el nivel que conoce el flujo completo. Las funciones internas pueden asumir que ya estan dentro de una transaccion si asi lo documentan.

## Regla para errores

Los servicios deben levantar excepciones de dominio o devolver resultados estructurados. Las vistas traducen esos errores a mensajes de usuario.

Evitar que servicios llamen `messages`, `render` o `redirect`.

## Regla para pruebas

Toda regla nueva debe tener prueba en el nivel mas bajo posible:

- Regla pura: prueba unitaria.
- Servicio con ORM: prueba de servicio.
- Flujo completo: prueba de integracion.
- Vista: prueba solo si el comportamiento HTTP es relevante.
