from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("ventas", "0002_notaventa_fisica"),
        ("catalogos", "0026_cliente_regimen_fiscal_json"),
    ]

    operations = [
        migrations.AlterField(
            model_name="clientecreditoautorizacion",
            name="venta_autorizada",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="autorizaciones_credito_usadas",
                to="ventas.notaventa",
            ),
        ),
    ]
