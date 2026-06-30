# Deuda tecnica SOLID identificada

Este documento registra puntos concretos que reducen el cumplimiento SOLID actual. No implica que el codigo este mal escrito; senala zonas donde el costo de cambio puede crecer si no se refactorizan con cuidado.

## Resumen

| Area | Riesgo principal | Principios afectados | Prioridad |
|---|---|---|---|
| Creacion de ventas | Fachada compatible; use case con puertos basicos | SRP, OCP, DIP | Media |
| Nota de venta vs inventario | Separacion fisica aplicada con compatibilidad legacy | SRP, DIP | Baja |
| Edicion de ventas | Fachada compatible; use cases separados para datos, precios y productos | SRP, OCP | Media |
| Catalogos views | Archivo monolitico con varios subdominios | SRP, ISP | Alta |
| Cliente fiscal | Modelo con logica fiscal y servicios | SRP, DIP | Alta |
| Dependencias entre apps | Acoplamiento directo entre dominios | DIP | Muy alta |
| Vistas de flujos grandes | Creacion/listado de ventas delegados a use case/selectors | SRP | Media |

## 1. `ventas/services/creacion.py`

### Problema

`VentaService` coordina varias responsabilidades:

- validacion de stock,
- validacion de credito,
- validacion de precio minimo,
- persistencia de la nota,
- entradas virtuales,
- descuento de inventario,
- registro de ultimo precio por cliente,
- comision por terminal,
- sincronizacion de pago en cartera.

Estado parcial: la comision y sincronizacion de pago terminal viven en `ventas/services/pagos.py`; la orquestacion de guardado vive en `ventas/use_cases/crear_nota_venta.py`; la validacion de precio, credito y stock vive en `ventas/services/validacion.py`. `VentaService` se mantiene como wrapper de compatibilidad. `CrearNotaVentaUseCase` ya acepta puertos basicos para stock, precio cliente y pago terminal con adaptadores por defecto.

### Riesgo

Cada nueva regla de venta tiende a modificar el mismo servicio. Esto aumenta el riesgo de regresiones y dificulta probar reglas aisladas.

### Refactor recomendado

Extraer servicios pequenos:

- `ValidarNotaVentaService`
- `PersistirNotaVentaService`
- `AfectarInventarioVentaService`
- `EntradaVirtualVentaService`
- `RegistrarPrecioClienteVentaService`
- `AplicarComisionVentaService` / `SincronizarPagoVentaService` aplicado como `ventas/services/pagos.py`

Use case orquestador creado:

- `CrearNotaVentaUseCase` en `ventas/use_cases/crear_nota_venta.py`

## 2. `ventas/services/edicion.py`

Estado: resuelto parcialmente. La entrada virtual de venta vive ahora en `ventas/services/inventario_virtual.py` y edicion ya no llama metodos privados de `VentaService`. Ademas, `ventas/services/edicion.py` quedo como fachada compatible que delega en `ventas/use_cases/editar_datos_nota.py`, `ventas/use_cases/ajustar_precios_nota.py` y `ventas/use_cases/agregar_productos_nota.py`.

### Problema original

El flujo de agregar productos reutiliza comportamiento de creacion mediante una llamada a un metodo privado:

```python
venta_service._registrar_entradas_virtuales(...)
```

### Riesgo

Un metodo privado no tiene contrato publico. Cambiar internamente `VentaService` puede romper edicion de ventas sin que sea evidente.

### Refactor aplicado

Se extrajo la regla a:

- `ventas/services/inventario_virtual.py`
- clase: `EntradaVirtualVentaService`

El servicio se usa desde creacion y edicion de ventas. Queda como mejora futura aplicar los mismos puertos de stock/precio/pago dentro de los use cases de edicion.

## 3. `ventas.models.NotaVenta` vs `inventarios.models.SalidaInventario`

Estado: aplicado en modo compatibilidad. `NotaVenta` dejo de ser proxy de `SalidaInventario` y ahora es una entidad comercial fisica ligada uno-a-uno al movimiento fisico de inventario mediante `salida`.

### Problema original

La nota comercial heredaba fisicamente de la misma tabla de salidas de inventario. Eso mezclaba identidad comercial, cliente, pago, cancelacion e impresion con el documento operativo que descuenta stock.

### Refactor aplicado

Se creo tabla propia de ventas y migracion de datos:

- `ventas.models.NotaVenta` conserva folio, cliente, pago, estado comercial, logo y metadatos de impresion.
- `inventarios.models.SalidaInventario` queda como movimiento fisico.
- Los detalles siguen en inventario y se acceden desde la nota a traves de `nota.salida.detalles`.
- Carteras y autorizaciones apuntan a `ventas.NotaVenta`.
- Se mantiene sincronizacion legacy hacia `SalidaInventario` para no romper reportes o integraciones que aun leen columnas antiguas.

### Riesgo restante

La compatibilidad legacy debe retirarse gradualmente cuando los reportes y flujos externos dejen de depender de campos comerciales en `SalidaInventario`.

## 4. `catalogos/views.py`

Estado: aplicado en modo compatibilidad. El archivo monolítico fue dividido en módulos `catalogos/views_*.py`; `catalogos/views.py` conserva imports públicos para no romper URLs ni imports históricos.

### Problema original

El archivo concentra multiples subdominios:

- categorias,
- productos,
- precios,
- bitacoras,
- clientes,
- almacenes,
- proveedores,
- parametros,
- importaciones,
- constancia fiscal.

### Riesgo

Cambios no relacionados comparten archivo, imports y helpers. Esto reduce cohesion y aumenta conflictos.

### Refactor aplicado

Se dividió en módulos compatibles con el archivo existente:

- `catalogos/views_categorias.py`
- `catalogos/views_productos.py`
- `catalogos/views_proveedores.py`
- `catalogos/views_proyectos.py`
- `catalogos/views_clientes.py`
- `catalogos/views_almacenes.py`
- `catalogos/views_importaciones.py`

`catalogos/views.py` se mantiene como fachada de compatibilidad durante la transición.

## 5. `catalogos/models.py` - `Cliente`

### Problema

El modelo `Cliente` contiene normalizacion fiscal, validacion fiscal y propiedades que llaman servicios de regimen fiscal.

### Riesgo

Cambios SAT/fiscales obligan a tocar el modelo principal de clientes. El modelo mezcla persistencia con transformacion y presentacion fiscal.

### Refactor recomendado

Crear:

- `catalogos/services/clientes_fiscales.py`

Con funciones como:

- `validar_regimen_fiscal_cliente(cliente)`
- `normalizar_regimen_fiscal_cliente(cliente)`
- `get_regimenes_fiscales_cliente(cliente)`
- `display_regimenes_fiscales_cliente(cliente)`

## 6. Dependencias cruzadas entre apps

### Problema

Existen dependencias concretas entre dominios:

- `ventas` llama cartera para pagos automaticos.
- `cartera` importa `ventas.models.NotaVenta`.
- `catalogos.services.credito_clientes` depende de selectores de cartera.
- `costos` lee ventas e inventarios.

### Riesgo

Parte del acoplamiento es normal en un monolito Django, pero las reglas variables quedan dificiles de sustituir en pruebas o futuras extensiones.

### Refactor recomendado

Introducir puertos internos:

- `PagoAutomaticoPort`
- `CreditoClientePort`
- `StockServicePort`
- `PrecioClientePort`
- `NotificadorPort`

Implementar adaptadores concretos por app.

## 7. Vistas de flujos grandes

### Problema

Algunas vistas aun calculan o coordinan demasiado:

- `cartera/views.py`
- `costos/views.py`
- partes de `catalogos/views.py`

Estado aplicado en ventas: `ventas/views/salidas.py` delega el POST a `CrearSalidaVentaWebUseCase`; `ventas/views/ventas.py` delega filtros, resumen y presentacion de almacen a `ventas/selectors/ventas.py`.

### Riesgo

Las reglas quedan acopladas a HTTP y son mas dificiles de probar sin request completo.

### Refactor recomendado

Crear use cases por flujo:

- `CrearSalidaVentaDesdeRequestUseCase`
- `RegistrarPagoClienteUseCase`
- `GenerarCosteoPeriodoUseCase`
- `ActualizarPrecioProductoUseCase`

## Politica de seguimiento

Cada vez que se resuelva una deuda:

1. Actualizar este documento.
2. Agregar o ajustar pruebas.
3. Revisar que el checklist SOLID siga cumpliendose.
4. Evitar mezclar el refactor con cambios funcionales no relacionados.
