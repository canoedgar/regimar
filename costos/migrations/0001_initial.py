# Generated manually for initial cost categories catalog.

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="CategoriaGasto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=120)),
                ("nombre_normalizado", models.CharField(editable=False, max_length=140, unique=True)),
                (
                    "tipo",
                    models.CharField(
                        choices=[
                            ("COMPRA", "Compra"),
                            ("OPERATIVO", "Operativo"),
                            ("ADMINISTRATIVO", "Administrativo"),
                            ("LOGISTICO", "Logístico"),
                            ("ALMACEN", "Almacén"),
                            ("REPARTO", "Reparto"),
                            ("FINANCIERO", "Financiero"),
                            ("OTRO", "Otro"),
                        ],
                        default="OPERATIVO",
                        max_length=20,
                    ),
                ),
                ("distribuible", models.BooleanField(default=True, help_text="Indica si los gastos de esta categoría participarán en el costeo real de productos.")),
                (
                    "metodo_default_distribucion",
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
                        help_text="Método sugerido al capturar un gasto de esta categoría.",
                        max_length=25,
                        verbose_name="Método default de distribución",
                    ),
                ),
                ("descripcion", models.TextField(blank=True)),
                ("activo", models.BooleanField(default=True)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("actualizado_en", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Categoría de gasto",
                "verbose_name_plural": "Categorías de gastos",
                "ordering": ["tipo", "nombre"],
                "permissions": [("puede_activar_categoriagasto", "Puede activar o desactivar categorías de gasto")],
            },
        ),
    ]
