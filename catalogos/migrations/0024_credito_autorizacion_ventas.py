# Generated manually during ventas bounded-context migration.
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("ventas", "0001_initial"),
        ("catalogos", "0023_rename_catalogos_c_cliente_e4cb8c_idx_catalogos_c_cliente_b63cba_idx_and_more"),
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
