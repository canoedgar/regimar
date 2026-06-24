# Generated manually for simplified cost flow.

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("catalogos", "0025_cliente_credito_defaults"),
        ("costos", "0007_alter_gastodistribucion_salida_detalle"),
    ]

    operations = [
        migrations.CreateModel(
            name="PeriodoCosteo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=120, verbose_name="Nombre")),
                ("fecha_inicio", models.DateField(db_index=True, verbose_name="Fecha inicio")),
                ("fecha_fin", models.DateField(db_index=True, verbose_name="Fecha fin")),
                ("fecha_corte_almacen", models.DateField(help_text="Fecha usada como referencia para calcular el costo de almacenaje.", verbose_name="Fecha corte almacén")),
                ("estado", models.CharField(choices=[("ABI", "Abierto"), ("REV", "En revisión"), ("CER", "Cerrado"), ("CAN", "Cancelado")], db_index=True, default="ABI", max_length=3, verbose_name="Estado")),
                ("notas", models.TextField(blank=True, verbose_name="Notas")),
                ("cerrado_en", models.DateTimeField(blank=True, null=True, verbose_name="Cerrado en")),
                ("cancelado_en", models.DateTimeField(blank=True, null=True, verbose_name="Cancelado en")),
                ("motivo_cancelacion", models.TextField(blank=True, verbose_name="Motivo de cancelación")),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("actualizado_en", models.DateTimeField(auto_now=True)),
                ("cancelado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="periodos_costeo_cancelados", to=settings.AUTH_USER_MODEL)),
                ("cerrado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="periodos_costeo_cerrados", to=settings.AUTH_USER_MODEL)),
                ("creado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="periodos_costeo_creados", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Periodo de costeo",
                "verbose_name_plural": "Periodos de costeo",
                "ordering": ["-fecha_inicio", "-id"],
                "permissions": [("puede_generar_costeo_periodo", "Puede generar costeo del periodo"), ("puede_cerrar_costeo_periodo", "Puede cerrar costeo del periodo"), ("puede_cancelar_costeo_periodo", "Puede cancelar costeo del periodo")],
                "unique_together": {("fecha_inicio", "fecha_fin")},
            },
        ),
        migrations.CreateModel(
            name="GastoPeriodo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo_gasto", models.CharField(choices=[("ALMACENAJE", "Almacenaje"), ("LUZ", "Luz"), ("NOMINA", "Nómina"), ("GASOLINA", "Gasolina"), ("MANTENIMIENTO", "Mantenimiento vehicular"), ("RENTA", "Renta"), ("ADMINISTRATIVO", "Administrativo"), ("OTRO", "Otro")], max_length=20, verbose_name="Tipo de gasto")),
                ("fecha", models.DateField(db_index=True, default=django.utils.timezone.now, verbose_name="Fecha del gasto")),
                ("importe", models.DecimalField(decimal_places=2, max_digits=14, validators=[MinValueValidator(Decimal("0.01"))], verbose_name="Importe")),
                ("referencia", models.CharField(blank=True, max_length=120, verbose_name="Referencia")),
                ("descripcion", models.TextField(blank=True, verbose_name="Descripción")),
                ("estado", models.CharField(choices=[("ACT", "Activo"), ("CAN", "Cancelado")], db_index=True, default="ACT", max_length=3, verbose_name="Estado")),
                ("motivo_cancelacion", models.TextField(blank=True, verbose_name="Motivo de cancelación")),
                ("cancelado_en", models.DateTimeField(blank=True, null=True, verbose_name="Cancelado en")),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("actualizado_en", models.DateTimeField(auto_now=True)),
                ("almacen", models.ForeignKey(blank=True, help_text="Opcional. Úsalo cuando el gasto corresponde a un almacén específico.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="gastos_periodo_costeo", to="catalogos.almacen", verbose_name="Almacén")),
                ("cancelado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="gastos_periodo_cancelados", to=settings.AUTH_USER_MODEL)),
                ("creado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="gastos_periodo_creados", to=settings.AUTH_USER_MODEL)),
                ("periodo", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="gastos", to="costos.periodocosteo", verbose_name="Periodo")),
                ("proveedor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="gastos_periodo_costeo", to="catalogos.proveedor", verbose_name="Proveedor")),
            ],
            options={
                "verbose_name": "Gasto del periodo",
                "verbose_name_plural": "Gastos del periodo",
                "ordering": ["-fecha", "-id"],
                "permissions": [("puede_cancelar_gasto_periodo", "Puede cancelar gastos del periodo")],
            },
        ),
        migrations.CreateModel(
            name="AlmacenajeProductoPeriodo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kg_al_corte", models.DecimalField(decimal_places=4, default=0, max_digits=18, verbose_name="Kg al corte")),
                ("tarifa_kg", models.DecimalField(decimal_places=6, default=0, max_digits=18, verbose_name="Tarifa por kg")),
                ("importe", models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name="Importe")),
                ("observaciones", models.TextField(blank=True, verbose_name="Observaciones")),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("almacen", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="almacenajes_costeo", to="catalogos.almacen", verbose_name="Almacén")),
                ("periodo", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="almacenajes", to="costos.periodocosteo", verbose_name="Periodo")),
                ("producto", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="almacenajes_costeo", to="catalogos.producto", verbose_name="Producto")),
            ],
            options={
                "verbose_name": "Almacenaje por producto",
                "verbose_name_plural": "Almacenaje por producto",
                "ordering": ["almacen__nombre", "producto__nombre"],
                "unique_together": {("periodo", "almacen", "producto")},
            },
        ),
        migrations.CreateModel(
            name="ResultadoCostoProducto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kg_vendidos", models.DecimalField(decimal_places=4, default=0, max_digits=18, verbose_name="Kg vendidos")),
                ("kg_almacenados", models.DecimalField(decimal_places=4, default=0, max_digits=18, verbose_name="Kg almacenados")),
                ("venta_total", models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name="Venta total")),
                ("costo_compra_total", models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name="Costo compra")),
                ("gastos_operativos", models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name="Gastos operativos")),
                ("costo_almacenaje", models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name="Costo almacenaje")),
                ("costo_real_total", models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name="Costo real total")),
                ("costo_real_unitario", models.DecimalField(decimal_places=6, default=0, max_digits=18, verbose_name="Costo real unitario")),
                ("utilidad_real", models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name="Utilidad real")),
                ("margen_real", models.DecimalField(decimal_places=2, default=0, max_digits=8, verbose_name="Margen real %")),
                ("costo_sugerido_siguiente", models.DecimalField(decimal_places=6, default=0, max_digits=18, verbose_name="Costo sugerido siguiente periodo")),
                ("aprobado", models.BooleanField(default=False, verbose_name="Aprobado")),
                ("aprobado_en", models.DateTimeField(blank=True, null=True, verbose_name="Aprobado en")),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("actualizado_en", models.DateTimeField(auto_now=True)),
                ("aprobado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="costos_producto_aprobados", to=settings.AUTH_USER_MODEL)),
                ("periodo", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="resultados", to="costos.periodocosteo", verbose_name="Periodo")),
                ("producto", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="resultados_costeo", to="catalogos.producto", verbose_name="Producto")),
            ],
            options={
                "verbose_name": "Resultado de costo por producto",
                "verbose_name_plural": "Resultados de costos por producto",
                "ordering": ["producto__nombre"],
                "unique_together": {("periodo", "producto")},
            },
        ),
        migrations.AddIndex(model_name="periodocosteo", index=models.Index(fields=["fecha_inicio", "fecha_fin"], name="costos_per_fecha_i_9b8f0a_idx")),
        migrations.AddIndex(model_name="periodocosteo", index=models.Index(fields=["estado"], name="costos_per_estado_589d62_idx")),
        migrations.AddIndex(model_name="gastoperiodo", index=models.Index(fields=["periodo", "estado"], name="costos_gas_periodo_2b9b57_idx")),
        migrations.AddIndex(model_name="gastoperiodo", index=models.Index(fields=["tipo_gasto", "fecha"], name="costos_gas_tipo_ga_c6bd91_idx")),
        migrations.AddIndex(model_name="almacenajeproductoperiodo", index=models.Index(fields=["periodo", "producto"], name="costos_alm_periodo_1be8d4_idx")),
        migrations.AddIndex(model_name="almacenajeproductoperiodo", index=models.Index(fields=["almacen", "producto"], name="costos_alm_almacen_245c36_idx")),
        migrations.AddIndex(model_name="resultadocostoproducto", index=models.Index(fields=["periodo", "producto"], name="costos_res_periodo_53c773_idx")),
        migrations.AddIndex(model_name="resultadocostoproducto", index=models.Index(fields=["producto"], name="costos_res_product_d43b82_idx")),
        migrations.AddIndex(model_name="resultadocostoproducto", index=models.Index(fields=["margen_real"], name="costos_res_margen__997d3d_idx")),
    ]
