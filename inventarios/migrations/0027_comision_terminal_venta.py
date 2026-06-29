# Generated manually for terminal commission persistence.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventarios", "0026_traspasos_inventario"),
    ]

    operations = [
        migrations.AddField(
            model_name="salidainventario",
            name="comision_terminal_porcentaje",
            field=models.DecimalField(
                decimal_places=4,
                default=0,
                help_text="Porcentaje de comisión de terminal aplicado históricamente a la nota.",
                max_digits=7,
                verbose_name="Comisión terminal (%)",
            ),
        ),
        migrations.AddField(
            model_name="salidainventario",
            name="comision_terminal_monto",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Importe de comisión de terminal aplicado a la nota.",
                max_digits=14,
                verbose_name="Comisión terminal",
            ),
        ),
        migrations.AlterField(
            model_name="salidainventario",
            name="forma_pago_venta",
            field=models.CharField(
                choices=[
                    ("CONTADO", "Contado"),
                    ("CREDITO", "Crédito"),
                    ("TERMINAL", "Terminal bancaria"),
                ],
                default="CONTADO",
                max_length=10,
                verbose_name="Forma de pago de venta",
            ),
        ),
    ]
