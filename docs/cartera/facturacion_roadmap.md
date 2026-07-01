# Roadmap de facturacion en cartera

## Objetivo

Agregar control manual de facturacion dentro del modulo de `cartera`, con XML guardado, vista previa imprimible/exportable a PDF, cancelacion de movimientos de facturacion, reportes por cliente y opcion para incluir facturacion en el estado de cuenta.

La primera version sera solo de control interno. No debe timbrar, cancelar ante SAT, contactar PAC ni afectar saldos, pagos, saldo a favor o estado de pago de notas.

## Hallazgos del modulo actual

### Piezas reutilizables

- `cartera.models.PagoCliente`: patron de encabezado de movimiento con cliente, fecha, estado, referencia, usuario creador y datos de cancelacion.
- `cartera.models.PagoAplicacionNota`: patron para aplicar un movimiento a una o varias `ventas.NotaVenta`.
- `cartera.services.cartera`: patron de casos de uso transaccionales y validaciones de negocio fuera de vistas.
- `cartera.selectors.cartera`: patron de consultas y agregados de lectura para estado de cuenta y reportes.
- `cartera.forms`: mixins reutilizables de fecha y seleccion de cliente.
- `cartera.views`: patron web actual: vista coordina request, form, selector, service, messages y template.
- Templates de impresion en `templates/cartera/prints/`: exportacion actual por vista imprimible con `window.print()`.
- `_empresa_contexto()` en `cartera.views`: datos de emisor reutilizables para vista previa/PDF.
- `catalogos.Cliente`: ya contiene RFC, nombre fiscal, regimen fiscal, CP fiscal, uso CFDI, email CFDI, forma/metodo de pago default.
- `catalogos.sat_catalogos`: choices SAT basicos ya disponibles para captura manual.

### Piezas que conviene no reutilizar directamente

- `PagoCliente`, `PagoAplicacionNota` y `ClienteSaldoFavorMovimiento` no deben mezclarse con facturacion. Su contrato actual impacta cartera y estados de pago.
- `get_estado_cuenta_cliente()` debe poder anexar facturacion opcionalmente, pero no convertir facturas en movimientos de cartera.
- El flujo XML historico de inventarios no debe retomarse como base funcional; los docs indican que fue retirado. Solo es referencia tecnica de campos, no de dominio.

## Modelo de dominio propuesto

### `FacturaCliente`

Encabezado del CFDI cargado manualmente.

Campos sugeridos:

- `cliente`: FK a `catalogos.Cliente`.
- `fecha`: fecha de emision del CFDI.
- `fecha_registro`: `auto_now_add`.
- `uuid`: UUID fiscal extraido del XML, unico para facturas activas o unico global si se desea evitar recaptura historica.
- `serie`, `folio`, `tipo_comprobante`, `moneda`.
- `subtotal`, `descuento`, `impuestos_trasladados`, `impuestos_retenidos`, `total`.
- `rfc_emisor`, `nombre_emisor`, `rfc_receptor`, `nombre_receptor`.
- `uso_cfdi`, `forma_pago`, `metodo_pago`.
- `xml`: `FileField(upload_to=...)` o texto XML si se decide guardar en BD. Recomendado: `FileField` para evitar crecer la base.
- `xml_hash`: hash SHA-256 para detectar duplicados de archivo.
- `estado`: `ACTIVA` / `CANCELADA`.
- `referencia`, `observaciones`.
- `creado_por`, `cancelado_por`, `cancelado_en`, `motivo_cancelacion`.

Validaciones estructurales:

- `total > 0`.
- XML requerido.
- UUID requerido si el XML lo contiene; si no se puede parsear, bloquear captura salvo decision explicita de negocio.
- Cliente del sistema debe coincidir con receptor por RFC cuando el cliente tenga RFC.

### `FacturaAplicacionNota`

Relacion entre factura y una o varias notas de venta.

Campos sugeridos:

- `factura`: FK a `FacturaCliente`.
- `nota_venta`: FK a `ventas.NotaVenta`.
- `monto_facturado`: monto aplicado a la nota.
- `creado_por`, `creado_en`.
- `observaciones`.

Reglas:

- La nota debe pertenecer al mismo cliente.
- La factura puede registrarse solo al cliente, sin notas, cuando sea una factura global/manual no conciliada.
- La suma aplicada a notas no debe exceder el total de la factura.
- La suma facturada contra una nota puede exceder el saldo pendiente de cartera, porque facturacion no afecta cartera; aun asi debe advertirse en UI si rebasa el total de la nota.

## Servicios propuestos

Crear `cartera/services/facturacion.py`.

Funciones publicas sugeridas:

- `registrar_factura_cliente(...)`: valida XML, crea `FacturaCliente` y aplicaciones opcionales a notas en una transaccion.
- `cancelar_factura_cliente(factura, usuario, motivo)`: marca cancelada, conserva XML y no elimina aplicaciones.
- `extraer_datos_cfdi(xml_file)`: parser acotado del XML CFDI 4.0/3.3 usando `xml.etree.ElementTree`, sin reglas web.
- `validar_factura_cliente(cliente, datos_cfdi)`: valida consistencia receptor/cliente y duplicados.

Mantener parsing y validacion de negocio separados para respetar SRP y facilitar pruebas.

## Selectors propuestos

Crear `cartera/selectors/facturacion.py`.

Consultas sugeridas:

- `get_facturas_cliente(cliente, incluir_canceladas=True)`.
- `get_facturacion_cliente_resumen(cliente)`: total facturado activo, cancelado, cantidad de facturas, ultimo CFDI.
- `get_facturas_nota(nota)`.
- `get_reporte_facturacion_por_cliente(fecha_inicio=None, fecha_fin=None, cliente_query="")`.
- `get_estado_facturacion_cliente(cliente)`: bloque opcional para anexar al estado de cuenta.

## Forms propuestos

Agregar en `cartera/forms.py` o separar a `cartera/forms_facturacion.py` si el archivo crece.

Formularios:

- `FacturaClienteForm`: cliente, XML, fecha opcional editable si se permite, referencia, observaciones.
- `FacturaAplicacionNotaFormSet`: notas del cliente y monto facturado.
- `CancelarFacturaForm`: motivo obligatorio con longitud minima.
- `ReporteFacturacionForm`: cliente, fecha inicio, fecha fin, estado.

Validacion de formato en forms; validacion de negocio en services.

## Vistas y URLs propuestas

URLs sugeridas:

- `facturas/` listado/busqueda general.
- `facturas/nueva/` cargar factura a cliente.
- `facturas/nota/<int:nota_id>/nueva/` cargar factura desde una nota.
- `facturas/<int:factura_id>/` detalle.
- `facturas/<int:factura_id>/preview/` vista previa imprimible/exportable a PDF.
- `facturas/<int:factura_id>/xml/` descarga del XML.
- `facturas/<int:factura_id>/cancelar/` cancelacion interna.
- `clientes/<int:cliente_id>/facturacion/` reporte por cliente.
- `reportes/facturacion-clientes/` reporte general con filtros.
- `reportes/facturacion-clientes/imprimir/` version imprimible.

Permisos nuevos:

- `puede_registrar_facturas`.
- `puede_cancelar_facturas`.
- `puede_ver_facturacion`.

## Estado de cuenta

Agregar parametro GET:

- `facturacion=1` para mostrar facturacion.
- Default recomendado: `0` para no cambiar el estado de cuenta actual.

Cambios:

- En `estado_cuenta_cliente` leer el parametro y, si esta activo, anexar `facturacion` al contexto desde selectors.
- En `estado_cuenta_cliente_print` preservar `facturacion=1` en el enlace de impresion.
- En template, agregar control tipo checkbox/toggle junto al filtro de movimientos.
- Mostrar seccion separada de facturas con folio/UUID, fecha, total, estado y notas relacionadas.
- No mezclar facturas en "Historial de pagos" ni "Movimientos de saldo a favor".

## Vista previa y PDF

Primera version:

- Reutilizar el patron de `templates/cartera/prints/*` y `window.print()`.
- Crear `templates/cartera/prints/factura_preview_print.html`.
- Renderizar datos del XML parseado y datos de empresa desde `_empresa_contexto()`.
- Boton "Imprimir / Guardar PDF".

Evolucion posterior:

- Evaluar generacion server-side con WeasyPrint/xhtml2pdf solo si se requiere PDF descargable real desde backend.
- Mantener interfaz de exportacion detras de un servicio/adaptador para no contaminar vistas ni servicios de negocio.

## Reportes

### Reporte por cliente

Debe incluir:

- Datos fiscales del cliente.
- Facturas activas y canceladas.
- Total facturado activo.
- Total cancelado.
- Notas relacionadas por factura.
- Enlace a XML y vista previa.

### Reporte general

Debe incluir:

- Filtro por fecha de emision.
- Filtro por cliente/RFC.
- Filtro por estado.
- Totales generales.
- Conteo de facturas.
- Acceso al detalle de cliente.

## Roadmap por fases

### Fase 0 - Validacion funcional

- Confirmar si una factura puede aplicar a varias notas y si una nota puede tener varias facturas.
- Confirmar si el UUID debe ser unico aunque la factura este cancelada.
- Confirmar si se soportaran CFDI 3.3 ademas de 4.0.
- Confirmar si se requiere guardar PDF generado o solo vista imprimible.
- Confirmar limite maximo de XML y politica de almacenamiento.

### Fase 1 - Base de dominio

- Crear modelos `FacturaCliente` y `FacturaAplicacionNota`.
- Crear migracion con indices por cliente, fecha, estado, UUID y nota.
- Registrar modelos en admin.
- Agregar permisos.
- Crear parser XML minimo y pruebas de parser.

### Fase 2 - Casos de uso manuales

- Implementar `registrar_factura_cliente`.
- Implementar `cancelar_factura_cliente`.
- Implementar forms de alta y cancelacion.
- Crear vistas de alta desde cliente/nota y detalle.
- Validar que no se modifiquen pagos, saldo a favor ni `estado_pago` de notas.

### Fase 3 - Consulta, vista previa y XML

- Crear selectors de facturacion.
- Crear detalle de factura.
- Crear descarga segura del XML.
- Crear vista previa imprimible/exportable a PDF.
- Agregar enlaces desde nota/estado de cuenta cuando aplique.

### Fase 4 - Estado de cuenta y reportes

- Agregar `facturacion=1` al estado de cuenta web.
- Agregar `facturacion=1` al estado de cuenta imprimible.
- Crear reporte de facturacion por cliente.
- Crear reporte general de facturacion.
- Agregar KPIs de facturacion en dashboard sin mezclar con cartera.

### Fase 5 - Endurecimiento

- Pruebas de servicios para registro, aplicacion a notas, duplicados y cancelacion.
- Pruebas de selectors para totales por cliente y filtros de reporte.
- Prueba de vista para que estado de cuenta oculte/muestre facturacion segun parametro.
- Validacion manual de PDF por navegador.
- Documentar deuda temporal si la exportacion sigue basada en `window.print()`.

## Riesgos y decisiones pendientes

- Validacion SAT: sin PAC, el sistema no puede garantizar vigencia real ni cancelar fiscalmente. La UI debe decir "Cancelacion interna" o "Control interno".
- XML mal formado: debe rechazarse para no guardar facturas imposibles de previsualizar.
- Duplicados: definir si se bloquea por UUID, por hash XML o ambos.
- Facturas globales: definir si se permitiran sin aplicaciones a notas.
- Parcialidades/complementos de pago: fuera de alcance inicial; no mezclarlos con pagos de cartera.
- Persistencia del XML: `FileField` es mas sano para base de datos, pero requiere revisar `MEDIA_ROOT` y respaldos.

## Checklist de aceptacion

- [ ] Se puede cargar XML manualmente para un cliente.
- [ ] Se puede aplicar la factura a una o varias notas del mismo cliente.
- [ ] Se puede registrar una factura solo al cliente sin afectar notas.
- [ ] Se guarda y puede descargarse el XML original.
- [ ] Se puede abrir vista previa e imprimir/guardar PDF desde navegador.
- [ ] Se puede cancelar internamente una factura con usuario, fecha y motivo.
- [ ] La cancelacion no borra XML ni aplicaciones.
- [ ] Facturacion no modifica pagos, saldo pendiente, saldo a favor ni estado de pago.
- [ ] El estado de cuenta oculta facturacion por default.
- [ ] El estado de cuenta muestra facturacion cuando `facturacion=1`.
- [ ] Existe reporte de facturacion por cliente.
- [ ] Existe reporte general de facturacion.
- [ ] Las reglas de negocio viven en services y las consultas en selectors.
- [ ] Hay pruebas de parser, registro, cancelacion y selectors principales.
