# Generated manually for expenses capture in cost module.

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("catalogos", "0023_rename_catalogos_c_cliente_e4cb8c_idx_catalogos_c_cliente_b63cba_idx_and_more"),
        ("inventarios", "0026_traspasos_inventario"),
        ("costos", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Gasto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("folio", models.CharField(blank=True, max_length=30, unique=True, verbose_name="Folio")),
                ("fecha", models.DateField(db_index=True, default=django.utils.timezone.now, verbose_name="Fecha del gasto")),
                ("periodo_inicio", models.DateField(db_index=True, verbose_name="Periodo inicio")),
                ("periodo_fin", models.DateField(db_index=True, verbose_name="Periodo fin")),
                (
                    "metodo_distribucion",
                    models.CharField(
                        choices=[
                            ("KG_VENDIDO", "Por kg vendido"),
                            ("IMPORTE_VENTA", "Por importe vendido"),
                            ("KG_COMPRADO", "Por kg comprado"),
                            ("COSTO_COMPRA", "Por costo de compra"),
                            ("DIRECTO_ENTRADA", "Directo a entrada"),
                            ("MANUAL", "Manual por producto"),
                            ("NO_DISTRIBUIR", "No distribuir"),
                        ],
                        default="KG_VENDIDO",
                        help_text="Método que se usará posteriormente para distribuir el gasto al costeo real.",
                        max_length=25,
                        verbose_name="Método de distribución",
                    ),
                ),
                (
                    "importe",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=14,
                        validators=[MinValueValidator(Decimal("0.01"))],
                        verbose_name="Importe",
                    ),
                ),
                (
                    "referencia",
                    models.CharField(
                        blank=True,
                        help_text="Factura, recibo, transferencia, nota o documento soporte.",
                        max_length=120,
                        verbose_name="Referencia",
                    ),
                ),
                ("descripcion", models.TextField(blank=True, verbose_name="Descripción")),
                ("observaciones", models.TextField(blank=True, verbose_name="Observaciones")),
                (
                    "estado",
                    models.CharField(
                        choices=[("BOR", "Borrador"), ("APL", "Aplicado"), ("CAN", "Cancelado")],
                        db_index=True,
                        default="BOR",
                        max_length=3,
                        verbose_name="Estado",
                    ),
                ),
                ("motivo_cancelacion", models.TextField(blank=True, verbose_name="Motivo de cancelación")),
                ("aplicado_en", models.DateTimeField(blank=True, null=True, verbose_name="Aplicado en")),
                ("cancelado_en", models.DateTimeField(blank=True, null=True, verbose_name="Cancelado en")),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("actualizado_en", models.DateTimeField(auto_now=True)),
                (
                    "almacen",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="gastos_costeo",
                        to="catalogos.almacen",
                        verbose_name="Almacén",
                    ),
                ),
                (
                    "aplicado_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="gastos_aplicados",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "cancelado_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="gastos_cancelados",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "categoria",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="gastos",
                        to="costos.categoriagasto",
                        verbose_name="Categoría",
                    ),
                ),
                (
                    "creado_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="gastos_creados",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "entrada_inventario",
                    models.ForeignKey(
                        blank=True,
                        help_text="Úsalo cuando el gasto pertenece directamente a una entrada, por ejemplo un flete de compra.",
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="gastos_costeo",
                        to="inventarios.entradainventario",
                        verbose_name="Entrada de inventario relacionada",
                    ),
                ),
                (
                    "proveedor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="gastos_costeo",
                        to="catalogos.proveedor",
                        verbose_name="Proveedor",
                    ),
                ),
            ],
            options={
                "verbose_name": "Gasto",
                "verbose_name_plural": "Gastos",
                "ordering": ["-fecha", "-creado_en"],
                "permissions": [("puede_aplicar_gasto", "Puede aplicar gastos"), ("puede_cancelar_gasto", "Puede cancelar gastos")],
                "indexes": [
                    models.Index(fields=["fecha", "estado"], name="costos_gast_fecha_d78658_idx"),
                    models.Index(fields=["periodo_inicio", "periodo_fin"], name="costos_gast_periodo_c34b1d_idx"),
                    models.Index(fields=["categoria", "estado"], name="costos_gast_categor_8494a7_idx"),
                ],
            },
        ),
    ]
