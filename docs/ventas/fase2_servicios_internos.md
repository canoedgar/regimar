# Fase 2 — Servicios internos de ventas

## Objetivo

Ordenar internamente el módulo `ventas` para que cada archivo represente un caso de uso o responsabilidad clara, manteniendo compatibilidad con los imports y rutas heredadas.

Esta fase no cambia modelos, rutas, templates ni comportamiento funcional.

## Cambios aplicados

### Creación de ventas

Se creó:

```text
ventas/services/creacion.py
```

Responsabilidad:

- Validar stock de la venta.
- Validar precio mínimo y crédito mediante servicios especializados.
- Guardar la nota de venta.
- Guardar detalles y asignaciones por almacén.
- Generar entrada automática cuando la venta usa almacén virtual.
- Descontar stock.
- Registrar último precio por cliente.

El archivo anterior:

```text
ventas/services/ventas.py
```

queda como wrapper de compatibilidad temporal.

---

### Edición de notas

Se creó:

```text
ventas/services/edicion.py
```

Responsabilidad:

- Editar datos administrativos de la nota.
- Ajustar precios de productos existentes.
- Agregar productos nuevos a una nota.
- Validar productos repetidos.
- Validar crédito durante edición.
- Registrar historial de precio por cliente.

El archivo anterior:

```text
ventas/services/notas_venta.py
```

queda como wrapper de compatibilidad temporal.

---

### Cancelación de notas

Se creó:

```text
ventas/services/cancelacion.py
```

Responsabilidad:

- Validar si una nota puede cancelarse.
- Calcular retornos de inventario por producto/almacén.
- Reintegrar stock.
- Marcar la nota como cancelada.
- Guardar motivo y fecha de cancelación.

La vista ahora solo obtiene la nota, llama al servicio y muestra mensajes.

---

### Impresión y expresiones de importes

Se creó:

```text
ventas/services/impresion.py
```

Responsabilidad:

- Centralizar la expresión de importe por línea.
- Centralizar la expresión de importe desde la nota hacia sus detalles.
- Obtener notas listas para impresión.
- Recargar la nota recién guardada con totales y detalles anotados.

Esto evita duplicar la regla:

```text
importe = cantidad base * precio unitario base
```

---

### API de precios por cliente

Se creó:

```text
ventas/services/precios_cliente.py
```

Responsabilidad:

- Construir el payload de precios vigentes por cliente/producto para la UI.
- Encapsular la consulta a `ClienteProductoPrecio` y el parámetro `PRECIO_VIGENCIA_DIAS`.

---

### Autorizaciones comerciales

Se creó:

```text
ventas/services/autorizaciones.py
```

Responsabilidad:

- Resolver autorización de precio mínimo.
- Resolver autorización extraordinaria de crédito.
- Exponer querysets base para las vistas de autorización.

La vista conserva solo la interacción HTTP: leer token, leer POST, mostrar plantilla o redirigir.

## Compatibilidad temporal

Se mantienen wrappers para no romper código existente:

```text
ventas/services/ventas.py
ventas/services/notas_venta.py
inventarios/services/ventas.py
inventarios/services/notas_venta.py
```

En fases posteriores estos wrappers deberán retirarse cuando todos los imports apunten a los servicios canónicos.

## Servicios canónicos después de esta fase

```text
ventas/services/creacion.py
ventas/services/edicion.py
ventas/services/cancelacion.py
ventas/services/impresion.py
ventas/services/precios_cliente.py
ventas/services/autorizaciones.py
ventas/services/venta_credito.py
ventas/services/venta_precio.py
ventas/services/venta_notificaciones.py
ventas/services/venta_data.py
ventas/services/venta_parser.py
```

## Validaciones recomendadas

```bash
python manage.py check
python manage.py test inventarios
python manage.py test ventas
python -m compileall -q ventas inventarios
```

## Pruebas manuales recomendadas

- Crear venta física.
- Crear venta con almacén virtual.
- Consultar precio por cliente en la captura.
- Autorizar precio menor al mínimo.
- Autorizar/rechazar venta extraordinaria por crédito.
- Editar datos de nota.
- Ajustar precios de nota.
- Agregar productos a nota.
- Cancelar nota.
- Imprimir nota recién generada.
- Listar notas con filtros.

## Estado SOLID

Esta fase mejora principalmente:

- **Single Responsibility:** cada servicio tiene un caso de uso más claro.
- **Open/Closed:** nuevas reglas de cancelación, impresión o autorización pueden modificarse en su archivo sin tocar creación de venta.
- **Interface Segregation:** las vistas dependen de servicios más pequeños.
- **Dependency Inversion:** se reduce la dependencia directa de las vistas hacia modelos y reglas de bajo nivel.
