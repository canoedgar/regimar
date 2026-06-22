# Generated manually for costos step 4: automatic expense distribution

from decimal import Decimal

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("catalogos", "0023_rename_catalogos_c_cliente_e4cb8c_idx_catalogos_c_cliente_b63cba_idx_and_more"),
        ("inventarios", "0026_traspasos_inventario"),
        ("costos", "0002_gasto"),
    ]

    operations = [
        migrations.CreateModel(
            name="GastoDistribucion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("metodo_distribucion", models.CharField(choices=[("KG_VENDIDO", "Por kg vendido"), ("IMPORTE_VENTA", "Por importe vendido"), ("KG_COMPRADO", "Por kg comprado"), ("COSTO_COMPRA", "Por costo de compra"), ("DIRECTO_ENTRADA", "Directo a entrada"), ("MANUAL", "Manual por producto"), ("NO_DISTRIBUIR", "No distribuir")], max_length=25, verbose_name="Método de distribución")),
                ("cantidad_base", models.DecimalField(decimal_places=4, help_text="Cantidad, importe o costo usado como base para prorratear el gasto.", max_digits=18, validators=[django.core.validators.MinValueValidator(Decimal("0.0001"))], verbose_name="Base de distribución")),
                ("porcentaje", models.DecimalField(decimal_places=6, default=0, max_digits=9, verbose_name="Porcentaje asignado")),
                ("importe_asignado", models.DecimalField(decimal_places=2, max_digits=14, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))], verbose_name="Importe asignado")),
                ("costo_unitario_asignado", models.DecimalField(decimal_places=6, default=0, max_digits=18, validators=[django.core.validators.MinValueValidator(Decimal("0.000000"))], verbose_name="Costo por unidad base")),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("almacen", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="gastos_distribuidos", to="catalogos.almacen", verbose_name="Almacén")),
                ("entrada_detalle", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="gastos_distribuidos", to="inventarios.entradainventariodetalle", verbose_name="Detalle de entrada")),
                ("gasto", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="distribuciones", to="costos.gasto", verbose_name="Gasto")),
                ("producto", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="gastos_distribuidos", to="catalogos.producto", verbose_name="Producto")),
                ("salida_detalle", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="gastos_distribuidos", to="inventarios.salidainventariodetalle", verbose_name="Detalle de salida")),
            ],
            options={
                "verbose_name": "Distribución de gasto",
                "verbose_name_plural": "Distribuciones de gastos",
                "ordering": ["producto__nombre", "almacen__nombre", "id"],
            },
        ),
        migrations.AddIndex(
            model_name="gastodistribucion",
            index=models.Index(fields=["gasto", "producto"], name="costos_gast_gasto_i_d0759d_idx"),
        ),
        migrations.AddIndex(
            model_name="gastodistribucion",
            index=models.Index(fields=["producto", "almacen"], name="costos_gast_product_5c0aca_idx"),
        ),
        migrations.AddIndex(
            model_name="gastodistribucion",
            index=models.Index(fields=["metodo_distribucion"], name="costos_gast_metodo__1486e3_idx"),
        ),
    ]
