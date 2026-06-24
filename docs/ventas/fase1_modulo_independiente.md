# Fase 1 — Módulo independiente de ventas

## Objetivo

Separar la capa comercial de ventas del módulo de inventarios sin cambiar todavía la tabla física donde viven las notas de venta.

Esta fase crea el contexto `ventas` como módulo Django funcional y deja a `inventarios` enfocado en entradas, salidas físicas, stock, ajustes, traspasos, kardex y costos.

## Alcance aplicado

- Se agregó `ventas` a `INSTALLED_APPS`.
- Se agregó `path("ventas/", include("ventas.urls"))`.
- Se creó `ventas/urls.py` con las rutas comerciales de venta.
- Se movieron vistas comerciales a `ventas/views/`.
- Se movieron servicios comerciales a `ventas/services/`.
- Se movieron selectors comerciales a `ventas/selectors/`.
- Se movieron formularios comerciales a `ventas/forms.py`.
- Se copiaron templates comerciales a `templates/ventas/`.
- Se crearon proxies de dominio:
  - `ventas.models.NotaVenta`
  - `ventas.models.NotaVentaDetalle`
- Se dejaron wrappers de compatibilidad en `inventarios` para no romper imports ni rutas antiguas.

## Decisión técnica importante

En esta fase **no se movieron físicamente las tablas** de notas de venta fuera de `inventarios`.

Las clases comerciales `NotaVenta` y `NotaVentaDetalle` son modelos proxy sobre:

- `inventarios.SalidaInventario`
- `inventarios.SalidaInventarioDetalle`

Esto evita romper:

- cartera,
- costos,
- dashboard,
- kardex,
- reportes,
- pruebas existentes,
- migraciones previas.

## Rutas

Rutas canónicas nuevas:

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

Rutas heredadas bajo `/inventarios/ventas/` y `/inventarios/salidas/venta/` se mantienen temporalmente por compatibilidad.

## Pendiente de fases posteriores

- Migrar gradualmente imports externos para que apunten a `ventas`.
- Separar permisos comerciales de los permisos `inventarios.*`.
- Crear pruebas propias en `ventas/tests.py`.
- Evaluar si conviene mantener los modelos como proxy o hacer migración física de tablas.
- Retirar rutas y wrappers heredados cuando ya no existan referencias activas.
