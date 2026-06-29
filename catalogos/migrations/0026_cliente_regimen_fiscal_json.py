# Generated manually for storing multiple SAT regimes in Cliente.regimen_fiscal.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalogos", "0025_cliente_credito_defaults"),
    ]

    operations = [
        migrations.AlterField(
            model_name="cliente",
            name="regimen_fiscal",
            field=models.TextField(
                blank=True,
                help_text=(
                    "JSON con uno o más regímenes fiscales SAT del cliente. "
                    "Ejemplo: [{\"codigo\":\"612\",\"descripcion\":\"Personas Físicas con Actividades Empresariales y Profesionales\"}]"
                ),
                verbose_name="Regímenes fiscales (SAT)",
            ),
        ),
    ]
