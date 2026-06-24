# Fase 3 — Migrar dependencias externas hacia ventas

## Objetivo

Hacer que los módulos externos traten las notas de venta como parte del dominio `ventas`, no como salidas de inventario.

En esta fase la base de datos todavía conserva las tablas físicas de inventarios mediante modelos proxy:

```text
ventas.NotaVenta -> inventarios.SalidaInventario tipo VTA
ventas.NotaVentaDetalle -> inventarios.SalidaInventarioDetalle de tipo VTA
```

## Cambios aplicados

### `ventas.models`

Se agregaron managers comerciales:

```text
NotaVentaManager
NotaVentaDetalleManager
```

Estos managers filtran automáticamente registros comerciales de venta:

```text
NotaVenta.objects -> tipo VTA
NotaVentaDetalle.objects -> salida tipo VTA
```

### `cartera`

Se actualizó el dominio de cartera para usar `ventas.NotaVenta` en lugar de `inventarios.SalidaInventario` cuando se habla de documentos por cobrar.

Archivos afectados:

```text
cartera/models.py
cartera/views.py
cartera/selectors/cartera.py
cartera/services/cartera.py
```

Se agregó migración:

```text
cartera/migrations/0004_relaciones_ventas.py
```

### `catalogos`

La autorización extraordinaria de crédito ahora apunta conceptualmente a `ventas.NotaVenta`.

Archivos afectados:

```text
catalogos/models.py
catalogos/migrations/0024_credito_autorizacion_ventas.py
```

### `costos`

Los cálculos y distribuciones basadas en ventas ahora usan `NotaVenta` y `NotaVentaDetalle`.

Archivos afectados:

```text
costos/models.py
costos/services/cierres.py
costos/services/distribucion.py
costos/migrations/0006_gastodistribucion_ventas.py
```

### `accounts / dashboard`

El dashboard ejecutivo y operativo ahora consulta ventas desde el dominio `ventas`.

Archivo afectado:

```text
accounts/views.py
```

También se actualizaron permisos base en:

```text
accounts/management/commands/inicializar_roles.py
```

### `notificaciones`

El bloque comercial del reporte general ahora usa `ventas.NotaVenta` y `ventas.NotaVentaDetalle`.

Archivo afectado:

```text
notificaciones/services/reportes.py
```

El bloque de salidas por tipo conserva `inventarios.SalidaInventario` porque representa movimientos generales de inventario.

### Permisos

Las vistas comerciales de ventas aceptan permisos nuevos de `ventas` y, temporalmente, permisos históricos de inventarios para no bloquear usuarios existentes durante la transición:

```text
ventas.view_notaventa / inventarios.view_salidainventario
ventas.add_notaventa / inventarios.add_salidainventario
ventas.change_notaventa / inventarios.change_salidainventario
```

## Lo que no cambia en esta fase

Esta fase no separa físicamente las tablas.

Todavía aplica:

```text
NotaVenta = proxy de SalidaInventario tipo VTA
```

La separación física se realizará en una fase posterior.

## Validaciones recomendadas

```bash
python manage.py check
python manage.py makemigrations --check
python manage.py migrate
python manage.py test ventas
python manage.py test inventarios
python manage.py test cartera
python manage.py test costos
python manage.py test
```

## Siguiente paso

Después de validar esta fase en entorno local, el siguiente paso del roadmap es:

```text
Fase 4 — Retirar wrappers de compatibilidad de inventarios
```
