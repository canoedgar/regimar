# Generated manually for costos step 5: cost period closing

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("catalogos", "0023_rename_catalogos_c_cliente_e4cb8c_idx_catalogos_c_cliente_b63cba_idx_and_more"),
        ("costos", "0003_gastodistribucion"),
    ]

    operations = [
        migrations.CreateModel(
            name="CierreCosteoPeriodo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("folio", models.CharField(blank=True, max_length=30, unique=True, verbose_name="Folio")),
                ("periodo_inicio", models.DateField(db_index=True, verbose_name="Periodo inicio")),
                ("periodo_fin", models.DateField(db_index=True, verbose_name="Periodo fin")),
                ("estado", models.CharField(choices=[("CER", "Cerrado"), ("CAN", "Cancelado")], db_index=True, default="CER", max_length=3, verbose_name="Estado")),
                ("total_productos", models.PositiveIntegerField(default=0, verbose_name="Productos")),
                ("total_movimientos_venta", models.PositiveIntegerField(default=0, verbose_name="Movimientos de venta")),
                ("total_ventas", models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name="Venta total")),
                ("total_costo_compra", models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name="Costo compra total")),
                ("total_gastos_distribuidos", models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name="Gastos distribuidos")),
                ("total_costo_real", models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name="Costo real total")),
                ("utilidad_bruta", models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name="Utilidad bruta")),
                ("utilidad_real", models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name="Utilidad real")),
                ("margen_bruto_porcentaje", models.DecimalField(decimal_places=2, default=0, max_digits=8, verbose_name="Margen bruto %")),
                ("margen_real_porcentaje", models.DecimalField(decimal_places=2, default=0, max_digits=8, verbose_name="Margen real %")),
                ("notas", models.TextField(blank=True, verbose_name="Notas")),
                ("motivo_cancelacion", models.TextField(blank=True, verbose_name="Motivo de cancelación")),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("cancelado_en", models.DateTimeField(blank=True, null=True, verbose_name="Cancelado en")),
                ("actualizado_en", models.DateTimeField(auto_now=True)),
                ("cancelado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="cierres_costeo_cancelados", to=settings.AUTH_USER_MODEL)),
                ("creado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="cierres_costeo_creados", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Cierre de costeo",
                "verbose_name_plural": "Cierres de costeo",
                "ordering": ["-periodo_inicio", "-folio"],
                "permissions": [("puede_cancelar_cierre_costeo", "Puede cancelar cierres de costeo")],
            },
        ),
        migrations.CreateModel(
            name="CierreCosteoProducto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("cantidad_vendida", models.DecimalField(decimal_places=4, default=0, max_digits=18, verbose_name="Cantidad vendida")),
                ("venta_total", models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name="Venta total")),
                ("costo_compra_total", models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name="Costo compra total")),
                ("gasto_asignado_total", models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name="Gasto asignado total")),
                ("costo_real_total", models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name="Costo real total")),
                ("utilidad_bruta", models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name="Utilidad bruta")),
                ("utilidad_real", models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name="Utilidad real")),
                ("precio_promedio", models.DecimalField(decimal_places=6, default=0, max_digits=18, verbose_name="Precio promedio")),
                ("costo_compra_unitario", models.DecimalField(decimal_places=6, default=0, max_digits=18, verbose_name="Costo compra unitario")),
                ("gasto_unitario", models.DecimalField(decimal_places=6, default=0, max_digits=18, verbose_name="Gasto unitario")),
                ("costo_real_unitario", models.DecimalField(decimal_places=6, default=0, max_digits=18, verbose_name="Costo real unitario")),
                ("margen_bruto_porcentaje", models.DecimalField(decimal_places=2, default=0, max_digits=8, verbose_name="Margen bruto %")),
                ("margen_real_porcentaje", models.DecimalField(decimal_places=2, default=0, max_digits=8, verbose_name="Margen real %")),
                ("movimientos_venta", models.PositiveIntegerField(default=0, verbose_name="Movimientos de venta")),
                ("cierre", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="productos", to="costos.cierrecosteoperiodo", verbose_name="Cierre")),
                ("producto", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="cierres_costeo", to="catalogos.producto", verbose_name="Producto")),
            ],
            options={
                "verbose_name": "Producto en cierre de costeo",
                "verbose_name_plural": "Productos en cierres de costeo",
                "ordering": ["producto__nombre"],
                "unique_together": {("cierre", "producto")},
            },
        ),
        migrations.AddIndex(
            model_name="cierrecosteoperiodo",
            index=models.Index(fields=["periodo_inicio", "periodo_fin"], name="costos_cier_periodo_7a9f5d_idx"),
        ),
        migrations.AddIndex(
            model_name="cierrecosteoperiodo",
            index=models.Index(fields=["estado"], name="costos_cier_estado_1ad5d8_idx"),
        ),
        migrations.AddIndex(
            model_name="cierrecosteoproducto",
            index=models.Index(fields=["cierre", "producto"], name="costos_cier_cierre__e08f0d_idx"),
        ),
        migrations.AddIndex(
            model_name="cierrecosteoproducto",
            index=models.Index(fields=["producto"], name="costos_cier_product_ef1860_idx"),
        ),
    ]
