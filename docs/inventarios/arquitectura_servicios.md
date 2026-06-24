# Arquitectura técnica del módulo de inventarios

## Objetivo del documento

Este documento describe la estructura técnica actual del módulo `inventarios`. Su objetivo es servir como referencia para mantenimiento, pruebas, revisión de errores y futuras extensiones del sistema.

El módulo conserva la responsabilidad principal de administrar existencias, movimientos de entrada, movimientos de salida, ajustes, traspasos, kardex, costos de inventario y afectaciones de stock generadas por ventas.

> Nota técnica: las ventas todavía se encuentran dentro de `inventarios`. Arquitectónicamente, el siguiente roadmap recomienda mover el dominio comercial a una app `ventas`, dejando en `inventarios` únicamente la afectación física o virtual de stock.

---

## Estructura general

```text
inventarios/
├── models.py
├── forms.py
├── urls.py
├── utils.py
├── tests.py
├── selectors/
│   ├── ajustes.py
│   ├── notas_venta.py
│   └── ventas.py
├── services/
│   ├── ajustes.py
│   ├── bitacora.py
│   ├── conversiones.py
│   ├── costos.py
│   ├── entradas_manual.py
│   ├── folios.py
│   ├── notas_venta.py
│   ├── reversas.py
│   ├── stock.py
│   ├── traspasos.py
│   ├── venta_credito.py
│   ├── venta_data.py
│   ├── venta_notificaciones.py
│   ├── venta_parser.py
│   ├── venta_precio.py
│   └── ventas.py
└── views/
    ├── ajustes.py
    ├── entradas.py
    ├── kardex.py
    ├── notas_edicion.py
    ├── salidas.py
    ├── traspasos.py
    └── ventas.py
```

---

## Responsabilidad por capa

### `models.py`

Contiene los modelos persistentes del módulo:

- `EntradaInventario`
- `EntradaInventarioDetalle`
- `SalidaInventario`
- `SalidaInventarioDetalle`
- `SalidaInventarioDetalleAlmacen`
- `InventarioStock`

Responsabilidades aceptadas en modelos:

- Definir campos y relaciones.
- Definir choices de tipo de movimiento.
- Validaciones estructurales con `clean()`.
- Propiedades simples, por ejemplo `logo_nota_static_path`.

Responsabilidades que no deben agregarse en modelos:

- Cálculo de costo promedio.
- Afectación de stock.
- Validaciones comerciales de venta.
- Envío de correos.
- Generación de movimientos compensatorios.

---

### `forms.py`

Contiene formularios de captura y validaciones propias de entrada de datos.

La lógica de negocio pesada no debe vivir aquí. El formulario puede validar datos requeridos o preparar valores, pero la creación de movimientos debe estar en servicios.

---

### `views/`

Las vistas tienen responsabilidad de orquestación web:

1. Recibir `request`.
2. Construir formularios o leer parámetros.
3. Llamar servicios/selectors.
4. Capturar errores controlados.
5. Renderizar template o redireccionar.

No deben concentrar reglas complejas de stock, costos, reversas o ventas.

---

### `selectors/`

Los selectors concentran consultas y armado de contexto de lectura para vistas o templates.

No deben modificar información ni generar movimientos.

---

### `services/`

Los servicios concentran casos de uso y reglas de negocio.

Son la capa recomendada para:

- Crear entradas.
- Crear salidas.
- Aplicar movimientos de stock.
- Recalcular costos.
- Validar crédito/precio.
- Crear reversas.
- Registrar traspasos.
- Coordinar ventas con inventario.

---

## Servicios principales

### `services/stock.py`

Responsabilidad: movimiento puro de existencias.

Funciones principales:

- `aplicar_movimiento_stock()`
- `agrupar_requeridos_por_producto()`
- `validar_stock_suficiente()`
- `errores_stock_humano()`
- `aplicar_movimientos_salida()`
- `aplicar_movimientos_entrada()`

Reglas importantes:

- `delta` positivo suma inventario.
- `delta` negativo descuenta inventario.
- No recalcula costos.
- No registra bitácora comercial.
- No actualiza último costo de compra.
- Lanza `IntegrityError` si el movimiento deja stock negativo.
- Actualiza `InventarioStock.cantidad` y `Producto.stock`.

Uso esperado:

```python
aplicar_movimiento_stock(
    producto_id=producto.id,
    almacen_id=almacen.id,
    delta=cantidad,
)
```

---

### `services/costos.py`

Responsabilidad: valorización del inventario.

Funciones principales:

- `costo_virtual_producto()`
- `costo_promedio_almacen()`
- `recalcular_costo_promedio_producto()`
- `aplicar_entrada_con_costo()`

Reglas importantes:

- `aplicar_entrada_con_costo()` suma inventario y recalcula costo promedio ponderado por almacén.
- Actualiza `InventarioStock.costo_promedio`.
- Actualiza `Producto.stock`.
- Puede actualizar `Producto.ultimo_costo_compra` y `Producto.fecha_ultima_compra`.
- Recalcula `Producto.costo_promedio` considerando existencias por almacén.
- No registra bitácora de precio; esa responsabilidad vive en `bitacora.py`.

Uso esperado:

```python
aplicar_entrada_con_costo(
    producto_id=producto.id,
    almacen_id=almacen.id,
    cantidad=cantidad_base,
    costo_unitario=costo_unitario,
)
```

---

### `services/bitacora.py`

Responsabilidad: aislar la dependencia con la bitácora de precios de catálogo.

Función principal:

- `registrar_bitacora_precio_inventario()`

Reglas importantes:

- Permite registrar bitácora usando `producto` o `producto_id`.
- Evita que `stock.py` dependa directamente de servicios comerciales de catálogo.
- Si no hay producto válido, no registra movimiento.

---

### `services/conversiones.py`

Responsabilidad: normalizar capturas de entrada a la métrica base del producto.

Función principal:

- `normalizar_captura_entrada()`

Reglas importantes:

- Convierte cantidades capturadas en presentación hacia cantidad base.
- Valida cantidades mayores a cero.
- Devuelve metadatos históricos de presentación:
  - nombre de presentación,
  - id de conversión,
  - cantidad capturada,
  - factor de conversión,
  - métrica base,
  - texto de equivalencia.

Uso esperado:

```python
captura = normalizar_captura_entrada(
    producto=producto,
    cantidad_capturada=cantidad,
    conversion_id_raw=conversion_id,
)
```

---

### `services/entradas_manual.py`

Responsabilidad: caso de uso de entrada manual de inventario.

Clase principal:

- `EntradaManualInventarioService`

Resultado:

- `EntradaManualResultado`

Métodos principales:

- `registrar_desde_form()`
- `normalizar_detalle()`

Reglas importantes:

- Recibe el formulario ya validado desde la vista.
- Interpreta el JSON de detalle.
- Normaliza líneas de productos.
- Soporta productos con peso variable.
- Soporta productos con conversión/presentación.
- Crea `EntradaInventario`.
- Crea `EntradaInventarioDetalle`.
- Aplica entrada con costo usando `aplicar_entrada_con_costo()`.
- Registra bitácora de precio mediante `registrar_bitacora_precio_inventario()`.
- Ejecuta la operación dentro de `transaction.atomic()`.

---

### `services/ajustes.py`

Responsabilidad: caso de uso de ajustes positivos y negativos.

Clase principal:

- `AjusteInventarioService`

Resultado:

- `AjusteInventarioResultado`

Métodos principales:

- `aplicar()`
- `preview()`
- `stock_actual()`

Reglas importantes:

- El ajuste en cero no se permite.
- El ajuste positivo crea `EntradaInventario` tipo ajuste positivo.
- El ajuste positivo usa conversión a métrica base.
- El ajuste positivo aplica costo con `aplicar_entrada_con_costo()`.
- El ajuste negativo crea `SalidaInventario` tipo ajuste negativo.
- El ajuste negativo valida stock por almacén antes de descontar.
- El ajuste negativo descuenta con `aplicar_movimiento_stock()`.
- El ajuste negativo recalcula costo promedio del producto.
- Registra bitácora de precio después del ajuste.

---

### `services/reversas.py`

Responsabilidad: reversar movimientos de inventario con movimientos compensatorios.

Clase principal:

- `ReversaInventarioService`

Resultado:

- `ReversaInventarioResultado`

Métodos principales:

- `reversar_entrada_manual()`
- `reversar_ajuste()`
- `entrada_manual_esta_reversada()`
- `ajuste_esta_reversado()`

Reglas importantes:

- No elimina movimientos originales.
- Crea movimientos compensatorios.
- Usa marcadores en observaciones con formato `REVERSA_DE=...`.
- Evita reversar dos veces el mismo movimiento.
- Valida que la reversa no deje inventario negativo.
- Recalcula costos cuando corresponde.

---

### `services/traspasos.py`

Responsabilidad: registrar traspasos entre almacenes.

Clase principal:

- `TraspasoInventarioService`

Resultado:

- `TraspasoInventarioResultado`

Reglas importantes:

- Valida producto, almacén origen, almacén destino y cantidad.
- No permite traspasar al mismo almacén.
- Valida que origen y destino permitan transferencias.
- Crea una salida tipo traspaso.
- Crea una entrada tipo traspaso.
- Relaciona ambos movimientos por folio y marcadores en observaciones.
- Descuenta stock del origen.
- Suma stock al destino respetando costo promedio del origen.
- No actualiza último costo de compra en el destino porque es un traspaso, no una compra.

---

### Responsabilidades comerciales movidas a `ventas`

A partir de la separación del dominio comercial, inventarios ya no mantiene wrappers de servicios de venta.

Los servicios canónicos viven en el módulo `ventas`:

- `ventas/services/creacion.py`
- `ventas/services/edicion.py`
- `ventas/services/cancelacion.py`
- `ventas/services/impresion.py`
- `ventas/services/precios_cliente.py`
- `ventas/services/autorizaciones.py`
- `ventas/services/venta_data.py`
- `ventas/services/venta_parser.py`
- `ventas/services/venta_credito.py`
- `ventas/services/venta_precio.py`
- `ventas/services/venta_notificaciones.py`

Inventarios conserva únicamente la responsabilidad de registrar movimientos, afectar stock, costos, kardex, entradas, salidas generales, ajustes y traspasos.

Cuando una venta requiere afectar inventario, el caso de uso de `ventas` coordina la operación y llama a los servicios de stock/costos de `inventarios`.

---

### `services/folios.py`

Responsabilidad: generación de folios de movimientos.

Funciones principales:

- `next_folio_movimiento()`
- `folio_reversa_unico()`

Reglas importantes:

- Genera folios únicos para movimientos de inventario.
- Centraliza folios de reversa.

---

## Selectors

### `selectors/ajustes.py`

Responsabilidad: consultas y presentación de ajustes recientes.

Funciones principales:

- `ajustes_recientes()`
- `conversion_ajuste_reciente()`
- `conversion_campos_ajuste_reciente()`

---

### Selectors comerciales movidos a `ventas`

Los selectors de contexto comercial ya no viven en inventarios.

Rutas canónicas:

- `ventas/selectors/ventas.py`
- `ventas/selectors/notas_venta.py`

Inventarios conserva sus selectors propios, como `inventarios/selectors/ajustes.py`, para consultas de movimientos y stock.

---

## Flujos principales

### Entrada manual

```text
views/entradas.py
  └── EntradaManualInventarioService.registrar_desde_form()
        ├── normalizar_detalle()
        ├── normalizar_captura_entrada()
        ├── EntradaInventario
        ├── EntradaInventarioDetalle
        ├── aplicar_entrada_con_costo()
        └── registrar_bitacora_precio_inventario()
```

---

### Ajuste positivo

```text
views/ajustes.py
  └── AjusteInventarioService.aplicar()
        ├── normalizar_captura_entrada()
        ├── EntradaInventario tipo AJP
        ├── EntradaInventarioDetalle
        ├── aplicar_entrada_con_costo()
        └── registrar_bitacora_precio_inventario()
```

---

### Ajuste negativo

```text
views/ajustes.py
  └── AjusteInventarioService.aplicar()
        ├── validar stock por almacén
        ├── SalidaInventario tipo AJN
        ├── SalidaInventarioDetalle
        ├── aplicar_movimiento_stock(delta negativo)
        ├── recalcular_costo_promedio_producto()
        └── registrar_bitacora_precio_inventario()
```

---

### Reversa

```text
views/ajustes.py / views/entradas.py
  └── ReversaInventarioService
        ├── validar que no exista reversa previa
        ├── validar stock suficiente
        ├── crear movimiento compensatorio
        ├── aplicar stock inverso
        └── recalcular costo cuando corresponde
```

---

### Traspaso

```text
views/traspasos.py
  └── TraspasoInventarioService.registrar_desde_form()
        ├── validar origen/destino/cantidad
        ├── crear salida por traspaso
        ├── crear entrada por traspaso
        ├── aplicar_movimiento_stock(origen, delta negativo)
        └── aplicar_entrada_con_costo(destino, actualizar_ultima_compra=False)
```

---

### Venta física

```text
ventas/views/salidas.py
  ├── VentaPostParser
  ├── VentaOperacionData
  └── VentaService
        ├── VentaPrecioMinimoService
        ├── VentaCreditoService
        ├── validar_stock_suficiente()
        ├── crear documento comercial proxy
        ├── crear salida/detalles de inventario tipo VTA
        ├── guardar asignaciones por almacén
        └── aplicar_movimientos_salida()
```

---

### Venta con almacén virtual

```text
ventas/views/salidas.py
  ├── VentaPostParser
  ├── VentaOperacionData
  └── VentaService
        ├── detecta almacén virtual
        ├── no bloquea por stock cero
        ├── crea entrada automática EV
        ├── aplica entrada con costo virtual
        ├── crea salida de venta
        └── aplica salida normal
```

---

## Pruebas automatizadas

El archivo `inventarios/tests.py` contiene pruebas para servicios críticos:

- Movimientos puros de stock.
- Stock insuficiente.
- Costo promedio ponderado.
- Costo promedio por producto usando almacenes.
- Costo virtual.
- Entrada manual.
- Ajuste positivo.
- Ajuste negativo.
- Bloqueo de ajuste en cero.
- Reversas.
- Traspasos.
- Venta física.
- Venta virtual.
- Precio mínimo.
- Delegación de crédito.

Comando recomendado:

```bash
python manage.py test inventarios
```

---

## Reglas de mantenimiento

1. Las vistas no deben volver a concentrar lógica de negocio.
2. Cualquier nuevo movimiento debe tener servicio propio o extender un servicio existente sin romper su responsabilidad.
3. Todo movimiento que afecte stock debe pasar por `stock.py` o `costos.py`, según corresponda.
4. Las entradas con costo deben usar `aplicar_entrada_con_costo()`.
5. Las salidas puras deben usar `aplicar_movimiento_stock()` o `aplicar_movimientos_salida()`.
6. Las reversas deben ser movimientos compensatorios; no deben eliminar movimientos históricos.
7. Las consultas reutilizables deben vivir en `selectors/`.
8. La lógica de presentación no debe agregarse a servicios.
9. La lógica de correo no debe agregarse a `VentaService`.
10. Antes de modificar reglas de stock, se deben ejecutar las pruebas de `inventarios`.

---

## Estado SOLID actual

| Principio | Estado actual | Comentario |
|---|---|---|
| Single Responsibility | Alto | Stock, costos, bitácora, ajustes, reversas y traspasos están separados. |
| Open/Closed | Bueno | Es posible agregar nuevos casos de uso mediante servicios. |
| Liskov | Aceptable | El módulo casi no usa herencia propia. |
| Interface Segregation | Bueno | La venta ya usa DTO/contexto en vez de depender directamente de `request`. |
| Dependency Inversion | Mejorado | Aún hay dependencia natural de modelos Django, pero se redujeron dependencias directas a correo, settings y request. |

---

## Pendientes conocidos

1. Separar ventas de inventarios en una app `ventas`.
2. Ajustar cartera para depender del dominio de ventas, no de `SalidaInventario`.
3. Mover autorizaciones comerciales de venta cuando exista la app `ventas`.
4. Ampliar pruebas cuando se separen los módulos.
5. Mantener documentación actualizada después de cada refactor.
