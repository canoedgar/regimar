# Generated manually for cliente credit defaults.
from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalogos", "0024_credito_autorizacion_ventas"),
    ]

    operations = [
        migrations.AlterField(
            model_name="cliente",
            name="limite_credito",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("3000.00"),
                help_text="Monto máximo autorizado de cartera. 0 = sin validación por monto.",
                max_digits=14,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
                verbose_name="Límite de crédito",
            ),
        ),
        migrations.AlterField(
            model_name="cliente",
            name="dias_credito",
            field=models.PositiveIntegerField(
                default=1,
                help_text="Días máximos permitidos para notas pendientes. 0 = sin validación por días.",
                verbose_name="Días de crédito",
            ),
        ),
    ]
