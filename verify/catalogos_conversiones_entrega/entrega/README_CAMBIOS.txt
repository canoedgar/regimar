Cambios realizados:
- Nuevo modelo: ProductoMetricaConversion
- Nueva migración: 0014_productometricaconversion.py
- ProductoForm ahora maneja conversiones mediante inline formset
- Ajuste de vistas create/edit/create_from_xml para guardar conversiones
- Ajuste de admin para administrar conversiones
- Ajuste de templates de productos para capturar y visualizar conversiones

Notas:
- No se ejecutó makemigrations ni migrate, como se solicitó.
- La métrica default sigue siendo la del producto (campo Producto.metrica).
- Cada conversión define cuánta métrica default representa una presentación no default.
  Ejemplo: nombre=Caja 10 kgs, unidad_origen=Caja, cantidad_origen=1, factor_conversion=10
