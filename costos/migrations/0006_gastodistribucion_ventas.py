# Generated manually during ventas bounded-context migration.
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("ventas", "0001_initial"),
        ("costos", "0005_rename_costos_cier_periodo_7a9f5d_idx_costos_cier_periodo_5a8f08_idx_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="gastodistribucion",
            name="salida_detalle",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="gastos_distribuidos",
                to="ventas.notaventadetalle",
                verbose_name="Detalle de nota de venta",
            ),
        ),
    ]
