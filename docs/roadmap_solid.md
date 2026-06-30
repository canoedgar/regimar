# Roadmap para mejorar cumplimiento SOLID

## Objetivo

Elevar el cumplimiento SOLID del proyecto desde el estado estimado actual, alrededor de 70%, hacia un nivel cercano a 95-100% en la práctica.

El 100% debe entenderse como una meta arquitectónica aspiracional: en un sistema Django con ORM activo, modelos relacionales y reglas de negocio reales, siempre existirán dependencias concretas razonables. El objetivo operativo es que las reglas críticas sean fáciles de extender, probar y mantener sin tocar módulos centrales innecesariamente.

## Estado actual estimado

| Principio | Cumplimiento actual | Meta |
|---|---:|---:|
| SRP - Single Responsibility | 72% | 95% |
| OCP - Open/Closed | 68% | 92% |
| LSP - Liskov Substitution | 80% | 95% |
| ISP - Interface Segregation | 72% | 95% |
| DIP - Dependency Inversion | 58% | 90% |
| Global | 70% | 94%+ |

## Principios guía

- Las vistas solo deben coordinar HTTP: request, formularios, servicios, mensajes y response.
- Los modelos deben contener estructura, validaciones invariantes y propiedades simples.
- Los servicios deben representar casos de uso concretos, no módulos generales con muchas razones de cambio.
- Las consultas complejas deben vivir en selectors.
- Los módulos de dominio no deben depender directamente de detalles de otros dominios cuando exista una regla de negocio intercambiable.
- Las integraciones internas entre apps deben pasar por servicios pequeños o puertos explícitos.
- Las pruebas deben cubrir reglas de negocio en servicios, no solo flujos completos.

## Fase 1 - Estabilizar fronteras y reglas de arquitectura

Prioridad: alta

Impacto esperado: 70% -> 76%

Documentos creados para esta fase:

- [Reglas de capas](arquitectura/capas.md)
- [Checklist SOLID](arquitectura/checklist_solid.md)
- [Deuda tecnica SOLID](arquitectura/deuda_tecnica_solid.md)

### Acciones

1. Definir una regla formal de capas en `docs/`:
   - `views` no contienen reglas de negocio.
   - `forms` validan captura, no ejecutan movimientos.
   - `models` no llaman servicios de negocio salvo normalizaciones muy simples.
   - `services` ejecutan casos de uso.
   - `selectors` solo leen.

2. Crear checklist de revisión para PRs o cambios:
   - ¿La vista solo orquesta?
   - ¿El servicio tiene una sola razón de cambio?
   - ¿Hay imports circulares o dependencias cruzadas evitables?
   - ¿Se está llamando un método privado desde otro módulo?
   - ¿La regla nueva tiene prueba unitaria?

3. Marcar como deuda técnica explícita los puntos actuales:
   - `ventas/services/creacion.py`
   - `ventas/services/edicion.py`
   - `catalogos/views.py`
   - `catalogos/models.py`, especialmente lógica fiscal de `Cliente`
   - dependencias cruzadas `ventas` <-> `cartera` <-> `catalogos`

### Criterio de salida

- Existe documentación clara de capas.
- Cada nuevo cambio puede evaluarse contra una regla concreta.
- No se agregan nuevas reglas de negocio a vistas grandes.

## Fase 2 - Separar casos de uso de ventas

Prioridad: muy alta

Impacto esperado: 76% -> 84%

### Problema

`VentaService` concentra demasiadas responsabilidades:

- validación de stock,
- validación de crédito,
- validación de precio mínimo,
- persistencia de nota,
- creación de entradas virtuales,
- descuento de inventario,
- registro de último precio,
- comisión de terminal,
- sincronización de pago automático.

Esto afecta SRP, OCP y DIP.

### Acciones

1. Dividir `VentaService` en casos de uso más pequeños:
   - `CrearNotaVentaUseCase`
   - `ValidarNotaVentaService`
   - `PersistirNotaVentaService`
   - `AfectarInventarioVentaService`
   - `RegistrarPrecioClienteVentaService`
   - `SincronizarPagoVentaService`
   - `AplicarComisionVentaService`

2. Mover `_registrar_entradas_virtuales` a un servicio público propio:
   - archivo sugerido: `ventas/services/inventario_virtual.py`
   - clase sugerida: `EntradaVirtualVentaService`

3. Eliminar llamadas a métodos privados entre servicios.
   - Caso actual a resolver: `ventas/services/edicion.py` llama `venta_service._registrar_entradas_virtuales(...)`.

4. Crear un orquestador del flujo de venta:
   - recibe dependencias,
   - llama servicios pequeños,
   - no contiene detalles de ORM de todos los subprocesos.

### Criterio de salida

- Ningún servicio de ventas supera aproximadamente 180-220 líneas salvo casos justificados.
- No hay llamadas a métodos privados de otros servicios.
- La creación de venta puede probarse con servicios colaboradores aislados.
- Agregar una nueva regla de comisión, crédito o inventario no requiere modificar el servicio principal completo.

## Fase 3 - Reducir lógica de negocio en vistas

Prioridad: alta

Impacto esperado: 84% -> 88%

### Problema

Hay vistas que todavía calculan, parsean y deciden reglas relevantes. Ejemplos:

- `ventas/views/salidas.py`
- `catalogos/views.py`
- `cartera/views.py`
- `costos/views.py`

### Acciones

1. Crear use cases para flujos web grandes:
   - `CrearSalidaVentaDesdeRequestUseCase`
   - `ActualizarPrecioProductoUseCase`
   - `CrearProductoConConversionesUseCase`
   - `RegistrarPagoClienteUseCase`

2. Mantener en vistas solamente:
   - construcción de forms,
   - llamada al caso de uso,
   - manejo de mensajes,
   - render o redirect.

3. En `catalogos/views.py`, separar por módulos:
   - `catalogos/views/productos.py`
   - `catalogos/views/clientes.py`
   - `catalogos/views/precios.py`
   - `catalogos/views/parametros.py`
   - `catalogos/views/importaciones.py`

4. Mover helpers de precio y stock visual a selectors o presenters:
   - `_preparar_stock_cajas`
   - `_parametro_decimal`
   - reglas de actualización de precio

### Criterio de salida

- Las vistas principales tienen menos decisiones de negocio.
- Los cambios de reglas comerciales se hacen en services/use cases.
- `catalogos/views.py` deja de ser un archivo monolítico.

## Fase 4 - Sacar lógica fiscal y comercial pesada de modelos

Prioridad: media-alta

Impacto esperado: 88% -> 91%

### Problema

`catalogos.models.Cliente` contiene lógica fiscal y llama servicios de regimen fiscal dentro de `clean`, `save` y propiedades. Esto mezcla persistencia, normalización fiscal y presentación.

### Acciones

1. Crear servicio de normalización fiscal:
   - `catalogos/services/clientes_fiscales.py`
   - funciones:
     - `normalizar_cliente_fiscal(cliente)`
     - `validar_regimen_fiscal_cliente(cliente)`
     - `get_regimenes_fiscales_cliente(cliente)`

2. Dejar en el modelo solo:
   - campos,
   - constraints,
   - normalizaciones invariantes mínimas,
   - propiedades simples sin dependencias complejas.

3. Mover displays complejos a presenters/selectors:
   - `ClienteFiscalPresenter`
   - o funciones selectoras para templates.

4. Revisar `Producto`, `Proyecto`, `Almacen` para mantener solo lógica estructural.

### Criterio de salida

- Los modelos no importan servicios complejos en métodos internos.
- La lógica fiscal se puede probar sin guardar necesariamente el modelo.
- Cambios SAT/fiscales no obligan a tocar el modelo principal salvo campos nuevos.

## Fase 5 - Invertir dependencias entre dominios

Prioridad: muy alta

Impacto esperado: 91% -> 95%

### Problema

Hay dependencias concretas entre apps:

- `ventas` llama `cartera`.
- `cartera` importa `ventas.models.NotaVenta`.
- `catalogos.services.credito_clientes` consulta cartera.
- `costos` depende de ventas e inventarios.

Algunas son razonables, pero varias reglas deberían depender de contratos, no de implementaciones concretas.

### Acciones

1. Crear puertos internos por dominio:
   - `ventas/ports.py`
   - `cartera/ports.py`
   - `inventarios/ports.py`
   - `catalogos/ports.py`

2. Definir interfaces simples con `typing.Protocol`, por ejemplo:
   - `StockServicePort`
   - `CreditoClientePort`
   - `PagoAutomaticoPort`
   - `PrecioClientePort`
   - `NotificadorPrecioMinimoPort`

3. Implementar adaptadores concretos:
   - `ventas/adapters/inventario.py`
   - `ventas/adapters/cartera.py`
   - `ventas/adapters/catalogos.py`

4. Inyectar dependencias en casos de uso:
   - constructor del use case,
   - factory local,
   - o contenedor simple de dependencias.

5. Evitar imports tardíos internos como solución permanente.
   - Los imports dentro de funciones pueden evitar ciclos, pero no resuelven DIP por sí mismos.

### Criterio de salida

- Las reglas de ventas dependen de puertos internos, no directamente de servicios concretos de cartera/inventario/catálogo.
- Las pruebas pueden sustituir adaptadores por fakes.
- Cambiar la forma de pagar, notificar o validar crédito no exige reescribir el flujo de venta.

## Fase 6 - Mejorar Open/Closed con estrategias

Prioridad: media

Impacto esperado: 95% -> 97%

### Acciones

1. Convertir reglas variables en estrategias:
   - cálculo de comisión por forma de pago,
   - validación de crédito,
   - autorización de precio mínimo,
   - costeo de inventario,
   - asignación de gastos,
   - selección de logo/plantilla de nota.

2. Reemplazar condicionales crecientes por registros de estrategias:
   - diccionarios de estrategia,
   - clases pequeñas,
   - factories.

3. Mantener defaults simples para no sobrediseñar:
   - no crear abstracciones donde solo hay una regla estable.

### Criterio de salida

- Agregar una nueva forma de comisión o regla de autorización requiere crear una estrategia nueva, no modificar un bloque central grande.
- Las reglas alternativas tienen pruebas aisladas.

## Fase 7 - Segregar interfaces y entradas de datos

Prioridad: media

Impacto esperado: 97% -> 98%

### Acciones

1. Reemplazar diccionarios grandes por DTOs/dataclasses donde el flujo sea crítico:
   - resultado de parseo de venta,
   - líneas de stock,
   - metadatos de presentación,
   - resultado de validación.

2. Separar interfaces de lectura y escritura:
   - selectors para consultas,
   - services para mutaciones,
   - presenters para datos de template.

3. Evitar que servicios reciban objetos demasiado amplios si solo necesitan pocos datos.
   - Por ejemplo, preferir `VentaRequestContext` antes que `request`.

### Criterio de salida

- Los servicios no dependen de `request` salvo adaptadores web.
- Los datos de entrada tienen estructura explícita.
- Las pruebas no necesitan construir requests completos para reglas de dominio.

## Fase 8 - Cobertura de pruebas orientada a SOLID

Prioridad: alta y continua

Impacto esperado: habilita todas las fases

### Acciones

1. Crear pruebas unitarias para servicios pequeños:
   - stock,
   - entrada virtual,
   - crédito,
   - precio mínimo,
   - comisión,
   - pago automático,
   - edición de nota.

2. Crear pruebas de integración para flujos completos:
   - crear venta normal,
   - crear venta con almacén virtual,
   - venta con comisión terminal,
   - venta con crédito excedido,
   - edición de nota con producto agregado,
   - cancelación de nota.

3. Usar fakes para puertos cuando se implemente DIP.

4. Medir cobertura de módulos críticos, no solo cobertura global.

### Criterio de salida

- Cada regla extraída queda cubierta por pruebas.
- Refactors de servicios no requieren probar manualmente todo el flujo web.
- Las pruebas documentan el comportamiento esperado.

## Orden recomendado de ejecución

1. Documentar reglas de capas y checklist.
2. Extraer entrada virtual de venta a servicio propio.
3. Dividir `VentaService`.
4. Reestructurar edición de venta para no depender de privados.
5. Reducir `ventas/views/salidas.py`.
6. Dividir `catalogos/views.py`.
7. Sacar lógica fiscal pesada de `Cliente`.
8. Introducir puertos para pagos, crédito, stock y notificaciones.
9. Convertir reglas variables a estrategias.
10. Separar fisicamente `NotaVenta` de `SalidaInventario`.
11. Reforzar pruebas por cada extracción.

## Backlog inicial sugerido

### Ticket 1 - Extraer entrada virtual de venta

Estado: aplicado.

Objetivo:
Crear `EntradaVirtualVentaService` y usarlo desde creación y edición.

Archivos objetivo:

- `ventas/services/creacion.py`
- `ventas/services/edicion.py`
- nuevo: `ventas/services/inventario_virtual.py`
- `ventas/tests.py`

Resultado esperado:

- Se elimina llamada a `_registrar_entradas_virtuales`.
- La regla de almacén virtual queda probada y reutilizable.

### Ticket 2 - Extraer sincronización de pago terminal

Estado: aplicado.

Objetivo:
Crear un servicio explícito para pago automático de venta terminal.

Archivos objetivo:

- `ventas/services/creacion.py`
- `ventas/services/edicion.py`
- nuevo: `ventas/services/pagos.py`

Resultado esperado:

- Ventas deja de importar cartera directamente en múltiples puntos.
- Se prepara el terreno para un `PagoAutomaticoPort`.

### Ticket 3 - Crear orquestador `CrearNotaVentaUseCase`

Estado: aplicado en modo compatibilidad. `VentaService.guardar()` delega en el use case; la vista podrá llamarlo directamente cuando la validación también quede separada.

Objetivo:
Reducir el tamaño y responsabilidades de `VentaService`.

Archivos objetivo:

- `ventas/services/creacion.py`
- nuevo: `ventas/use_cases/crear_nota_venta.py`

Resultado esperado:

- La vista llama un caso de uso.
- Los servicios internos quedan enfocados.

### Ticket 3.1 - Separar validación de venta

Estado: aplicado en modo compatibilidad. `VentaService.validar_stock()` delega en `ValidarNotaVentaService`; la vista podrá usarlo directamente cuando retiremos el wrapper.

Objetivo:
Extraer validación de precio mínimo, crédito y stock físico a un servicio propio.

Archivos objetivo:

- `ventas/services/creacion.py`
- nuevo: `ventas/services/validacion.py`

Resultado esperado:

- La validación queda reutilizable fuera de `VentaService`.
- Se prepara el retiro gradual de `VentaService` como fachada temporal.


### Ticket 3.2 - Delegar creación web de venta

Estado: aplicado. `ventas/views/salidas.py` delega la interpretación del POST y la creación de la nota en `ventas/use_cases/crear_salida_venta_web.py`.

Resultado esperado:

- La vista solo coordina HTTP, formularios, mensajes y render.
- El parsing, cálculo de total para validación y persistencia quedan fuera de la vista.

### Ticket 3.3 - Separar edición de notas de venta

Estado: aplicado en modo compatibilidad. `ventas/services/edicion.py` conserva las clases públicas, pero delega en use cases específicos.

Archivos creados:

- `ventas/use_cases/editar_datos_nota.py`
- `ventas/use_cases/ajustar_precios_nota.py`
- `ventas/use_cases/agregar_productos_nota.py`
- `ventas/services/marcado.py`

Resultado esperado:

- Menos razones de cambio en `ventas/services/edicion.py`.
- Los flujos de datos, precios y productos pueden evolucionar por separado.

### Ticket 3.4 - Introducir puertos básicos de venta

Estado: aplicado parcialmente. `CrearNotaVentaUseCase` acepta puertos para stock, precio cliente y pago terminal, con adaptadores por defecto.

Archivos creados:

- `ventas/ports.py`
- `ventas/adapters/inventario.py`
- `ventas/adapters/catalogos.py`
- `ventas/adapters/pagos.py`

Resultado esperado:

- La creación de ventas empieza a depender de contratos sustituibles.
- Las pruebas futuras podrán inyectar fakes sin tocar inventarios, catálogo o cartera.

### Ticket 3.5 - Mover consultas del listado de ventas a selectors

Estado: aplicado. `ventas/views/ventas.py` delega filtros, agregados, paginación y display de almacén a `ventas/selectors/ventas.py`.

Resultado esperado:

- La vista del listado queda enfocada en renderizar.
- Las consultas complejas quedan en la capa de lectura.

### Ticket 3.6 - Aislar afectaciones de inventario

Estado: aplicado parcialmente. `inventarios/services/afectaciones.py` centraliza operaciones de stock, costo y bitácora usadas por ajustes y reversas.

Resultado esperado:

- `AjusteInventarioService` y `ReversaInventarioService` reducen dependencias concretas directas.
- La política de afectación de stock/costo queda en un colaborador pequeño.

### Ticket 3.7 - Separar fisicamente `NotaVenta` de `SalidaInventario`

Estado: aplicado en modo compatibilidad. `ventas.NotaVenta` ahora tiene tabla propia y una relacion uno-a-uno con `inventarios.SalidaInventario`, que queda como movimiento fisico de stock.

Archivos principales:

- `ventas/models.py`
- `ventas/migrations/0002_notaventa_fisica.py`
- `cartera/migrations/0005_notaventa_fisica_fk.py`
- `catalogos/migrations/0027_notaventa_fisica_fk.py`
- selectors, forms, services y vistas de `ventas`/`cartera`

Resultado esperado:

- La venta comercial puede evolucionar sin modificar el modelo operativo de inventario.
- Cartera y autorizaciones referencian la entidad comercial correcta.
- Se conserva sincronizacion legacy mientras se retiran dependencias antiguas sobre columnas comerciales de `SalidaInventario`.

### Ticket 4 - Dividir `catalogos/views.py`

Estado: aplicado en modo compatibilidad. `catalogos/views.py` queda como fachada y las implementaciones viven en módulos `catalogos/views_*.py`.

Objetivo:
Separar vistas por subdominio.

Archivos objetivo:

- `catalogos/views.py`
- nuevos módulos `catalogos/views_*.py`
- `catalogos/views.py` como fachada compatible

Resultado esperado:

- Cada archivo de vista tiene una responsabilidad clara.
- Menor riesgo al modificar clientes, productos o precios.

### Ticket 5 - Extraer fiscalidad de `Cliente`

Objetivo:
Mover normalización y display fiscal a servicios/presenters.

Archivos objetivo:

- `catalogos/models.py`
- `catalogos/services/regimenes_fiscales.py`
- nuevo: `catalogos/services/clientes_fiscales.py`

Resultado esperado:

- `Cliente` queda más cercano a modelo persistente.
- Cambios fiscales se aíslan mejor.

## Meta realista

Al completar las fases 1 a 5, el proyecto debería quedar cerca de:

| Principio | Meta realista |
|---|---:|
| SRP | 92-95% |
| OCP | 88-92% |
| LSP | 90-95% |
| ISP | 90-95% |
| DIP | 85-90% |
| Global | 90-94% |

Para acercarse más a 100%, las fases 6 a 8 deben consolidar estrategias, puertos y pruebas. La prioridad no debe ser perseguir abstracciones por estética, sino reducir el costo de cambio en reglas reales del negocio.
