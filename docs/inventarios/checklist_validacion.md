# Checklist de validación técnica del módulo de inventarios

## Objetivo

Este checklist debe ejecutarse después de aplicar cambios en inventarios para confirmar que el módulo sigue funcionando correctamente a nivel técnico y operativo.

---

## 1. Validaciones técnicas Django

Ejecutar desde la raíz del proyecto, con el entorno virtual activo:

```bash
python manage.py check
python manage.py makemigrations --check
python manage.py showmigrations inventarios
python manage.py test inventarios
```

Resultado esperado:

- `check` sin errores.
- `makemigrations --check` sin migraciones pendientes.
- Migraciones de `inventarios` en estado aplicado en el entorno correspondiente.
- Pruebas de `inventarios` pasando correctamente.

---

## 2. Validación de sintaxis rápida

Cuando solo se quiere verificar sintaxis Python:

```bash
python -m compileall -q inventarios
```

Resultado esperado:

- El comando termina sin mostrar errores.

---

## 3. Validación de limpieza del flujo XML/factura

El flujo de entrada por factura/XML fue retirado. Validar que no existan referencias activas a componentes propios de ese flujo:

```text
facturaentrada
xml_contenido
uuid_factura
TIPO_OC_CON_FACTURA
OCF
inventarios/services/cfdi.py
templates/inventarios/entrada_ocf_form.html
```

No usar una búsqueda genérica de `cfdi`, porque el sistema conserva campos fiscales legítimos de clientes como `uso_cfdi_default` y `email_cfdi`.

Comandos sugeridos:

```bash
grep -R "facturaentrada\|xml_contenido\|uuid_factura\|TIPO_OC_CON_FACTURA\|OCF" inventarios templates static --exclude-dir=__pycache__
test ! -f inventarios/services/cfdi.py
test ! -f templates/inventarios/entrada_ocf_form.html
```

Resultado esperado:

- Sin coincidencias activas en archivos fuente para los términos del flujo XML eliminado.
- El archivo `inventarios/services/cfdi.py` no existe.
- El template `templates/inventarios/entrada_ocf_form.html` no existe.

---

## 4. Flujos manuales a probar desde la aplicación

### Entrada manual

Validar:

- Crear entrada manual con proveedor.
- Capturar producto con métrica base.
- Capturar producto con presentación/conversión.
- Capturar producto de peso variable, si aplica.
- Confirmar que aumenta stock en el almacén seleccionado.
- Confirmar que se actualiza costo promedio.
- Confirmar que aparece en listado y detalle de entradas.

---

### Reversa de entrada manual

Validar:

- Reversar entrada manual.
- Confirmar que genera salida compensatoria.
- Confirmar que descuenta stock.
- Confirmar que no permite reversar dos veces.
- Confirmar que no permite reversar si dejaría stock negativo.

---

### Ajuste positivo

Validar:

- Aplicar ajuste positivo.
- Confirmar que genera entrada tipo ajuste positivo.
- Confirmar conversión a métrica base.
- Confirmar que aumenta stock.
- Confirmar que actualiza costo promedio.
- Confirmar preview correcto antes de guardar.

---

### Ajuste negativo

Validar:

- Aplicar ajuste negativo.
- Confirmar que genera salida tipo ajuste negativo.
- Confirmar que descuenta stock.
- Confirmar que bloquea stock insuficiente.
- Confirmar que no permite cantidad cero.
- Confirmar preview correcto antes de guardar.

---

### Reversa de ajuste

Validar:

- Reversar ajuste positivo.
- Reversar ajuste negativo.
- Confirmar que crea movimiento compensatorio.
- Confirmar que no permite reversar dos veces.
- Confirmar que no deja stock negativo.

---

### Traspaso

Validar:

- Crear traspaso entre almacenes diferentes.
- Confirmar que genera salida por traspaso.
- Confirmar que genera entrada por traspaso.
- Confirmar que descuenta origen.
- Confirmar que suma destino.
- Confirmar que conserva costo promedio del origen.
- Confirmar que no permite mismo almacén.
- Confirmar que respeta `permite_transferencias` de origen/destino.

---

### Venta física

Validar:

- Crear venta con stock suficiente.
- Confirmar que genera salida tipo venta.
- Confirmar que descuenta stock del almacén seleccionado.
- Confirmar que guarda detalle y asignación por almacén.
- Confirmar que registra último precio por cliente.
- Confirmar impresión de nota.

---

### Venta con almacén virtual

Validar:

- Crear venta desde almacén virtual o virtual de sistema.
- Confirmar que no bloquea por stock cero.
- Confirmar que crea entrada automática con folio prefijo `EV`.
- Confirmar que crea salida de venta.
- Confirmar que el stock neto no queda negativo.
- Confirmar que queda trazabilidad entrada/salida.

---

### Validación de precio mínimo

Validar:

- Crear venta con precio menor al mínimo.
- Confirmar que pide autorización.
- Confirmar generación de autorización cuando se confirma envío.
- Confirmar envío o manejo controlado del correo.
- Confirmar que el token de autorización funciona.

---

### Validación de crédito

Validar:

- Cliente sin límite configurado.
- Cliente con límite configurado y saldo permitido.
- Cliente con límite excedido.
- Cliente con días de crédito vencidos.
- Autorización extraordinaria.
- Marcado de autorización usada al guardar venta.

---

## 5. Pruebas automatizadas cubiertas

El archivo `inventarios/tests.py` contiene cobertura para:

- `StockServiceTests`
- `CostosServiceTests`
- `EntradaManualInventarioServiceTests`
- `AjusteInventarioServiceTests`
- `ReversaInventarioServiceTests`
- `TraspasoInventarioServiceTests`
- `VentaServiceTests`
- `VentaPrecioMinimoServiceTests`
- `VentaCreditoServiceTests`

Ejecutar:

```bash
python manage.py test inventarios
```

---

## 6. Criterios de aceptación del cierre técnico

La Fase 0 de cierre técnico de inventarios se considera completa cuando:

- La documentación técnica existe en `docs/inventarios/arquitectura_servicios.md`.
- Este checklist existe en `docs/inventarios/checklist_validacion.md`.
- `python -m compileall -q inventarios` no muestra errores.
- `python manage.py check` pasa en el entorno del proyecto.
- `python manage.py test inventarios` pasa en el entorno del proyecto.
- Los flujos manuales críticos fueron probados.
- No existen referencias activas al flujo XML/factura eliminado.

---

## 7. Próximo paso recomendado

Después de cerrar esta validación, el siguiente roadmap recomendado es separar ventas en una app independiente:

```text
ventas/
```

Inventarios debe conservar la afectación de stock por venta, pero el dominio comercial debe salir gradualmente de `inventarios`.
