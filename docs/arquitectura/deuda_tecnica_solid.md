# Deuda tecnica SOLID identificada

Este documento registra puntos concretos que reducen el cumplimiento SOLID actual. No implica que el codigo este mal escrito; senala zonas donde el costo de cambio puede crecer si no se refactorizan con cuidado.

## Resumen

| Area | Riesgo principal | Principios afectados | Prioridad |
|---|---|---|---|
| Creacion de ventas | Servicio con demasiadas responsabilidades | SRP, OCP, DIP | Muy alta |
| Edicion de ventas | Reutilizacion mediante metodo privado | SRP, OCP | Muy alta |
| Catalogos views | Archivo monolitico con varios subdominios | SRP, ISP | Alta |
| Cliente fiscal | Modelo con logica fiscal y servicios | SRP, DIP | Alta |
| Dependencias entre apps | Acoplamiento directo entre dominios | DIP | Muy alta |
| Vistas de flujos grandes | Orquestacion web con calculos de negocio | SRP | Media-alta |

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

Estado parcial: la comision y sincronizacion de pago terminal ya fueron extraidas a `ventas/services/pagos.py` en el Ticket 2 de Fase 2. La orquestacion de guardado fue movida a `ventas/use_cases/crear_nota_venta.py` en el Ticket 3 de Fase 2, manteniendo `VentaService.guardar()` como wrapper de compatibilidad. La validacion de precio, credito y stock fue extraida a `ventas/services/validacion.py`, manteniendo `VentaService.validar_stock()` como wrapper de compatibilidad.

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

Estado: resuelto en el Ticket 1 de Fase 2. La entrada virtual de venta vive ahora en `ventas/services/inventario_virtual.py` y edicion ya no llama metodos privados de `VentaService`.

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

El servicio se usa desde creacion y edicion de ventas.

## 3. `catalogos/views.py`

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

## 4. `catalogos/models.py` - `Cliente`

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

## 5. Dependencias cruzadas entre apps

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

## 6. Vistas de flujos grandes

### Problema

Algunas vistas aun calculan o coordinan demasiado:

- `ventas/views/salidas.py`
- `cartera/views.py`
- `costos/views.py`
- partes de `catalogos/views.py`

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
