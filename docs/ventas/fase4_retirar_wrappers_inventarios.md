# Fase 4 — Retirar wrappers de compatibilidad de inventarios

## Objetivo

Eliminar los puentes temporales que permitían usar ventas desde rutas, servicios, selectors y templates de `inventarios`.

Después de esta fase, las rutas comerciales canónicas son las de `ventas`:

```text
/ventas/
/ventas/nueva/
/ventas/notas/<id>/acciones/
/ventas/notas/<id>/editar-datos/
/ventas/notas/<id>/ajustar-precios/
/ventas/notas/<id>/agregar-productos/
/ventas/notas/<id>/cancelar/
/ventas/notas/<id>/imprimir/
```

## Cambios aplicados

### Rutas

Se retiraron de `inventarios/urls.py` las rutas heredadas:

```text
/inventarios/ventas/
/inventarios/ventas/notas/...
/inventarios/salidas/venta/nueva/
/inventarios/salidas/venta/precios-cliente/
/inventarios/salidas/venta/autorizar-precio/...
/inventarios/salidas/venta/autorizacion-cartera/...
```

Las rutas activas viven en `ventas/urls.py`.

### Vistas y servicios

Se retiraron wrappers de compatibilidad en inventarios:

```text
inventarios/views/ventas.py
inventarios/views/notas_edicion.py
inventarios/services/ventas.py
inventarios/services/notas_venta.py
inventarios/services/venta_credito.py
inventarios/services/venta_data.py
inventarios/services/venta_notificaciones.py
inventarios/services/venta_parser.py
inventarios/services/venta_precio.py
inventarios/selectors/ventas.py
inventarios/selectors/notas_venta.py
```

También se retiró de `inventarios/views/salidas.py` la reexportación temporal de vistas comerciales.

### Formularios

Se retiró de `inventarios/forms.py` la reexportación temporal de formularios comerciales.

Los formularios canónicos viven en:

```text
ventas/forms.py
```

### Templates

Se eliminaron los duplicados comerciales bajo `templates/inventarios/`.

Los templates canónicos viven en:

```text
templates/ventas/
```

### Permisos

Las vistas de ventas ahora validan permisos del módulo `ventas` directamente:

```text
ventas.view_notaventa
ventas.add_notaventa
ventas.change_notaventa
```

El menú de ventas y el dashboard ya no usan permisos de `inventarios.salidainventario` como fallback comercial.

## Lo que no cambia

Esta fase no separa físicamente las tablas de base de datos.

Todavía aplica:

```text
ventas.NotaVenta -> proxy de inventarios.SalidaInventario tipo VTA
ventas.NotaVentaDetalle -> proxy de inventarios.SalidaInventarioDetalle tipo VTA
```

La separación física queda pendiente para la siguiente fase.

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

## Pruebas manuales recomendadas

- Abrir `/ventas/`.
- Crear una venta desde `/ventas/nueva/`.
- Imprimir una nota.
- Editar datos de una nota.
- Ajustar precios de una nota.
- Agregar productos a una nota.
- Cancelar una nota.
- Validar que `/inventarios/` conserva entradas, salidas, ajustes, traspasos y kardex.
- Validar que las rutas heredadas `/inventarios/ventas/` y `/inventarios/salidas/venta/nueva/` ya no sean usadas por menú ni dashboard.

## Siguiente paso

Después de validar esta fase, el siguiente paso del roadmap es:

```text
Fase 5 — Separación física de ventas e inventarios en base de datos
```
