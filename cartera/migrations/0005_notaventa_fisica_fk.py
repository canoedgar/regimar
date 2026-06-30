from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("ventas", "0002_notaventa_fisica"),
        ("cartera", "0004_relaciones_ventas"),
    ]

    operations = [
        migrations.AlterField(
            model_name="pagoaplicacionnota",
            name="nota_venta",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="aplicaciones_cartera",
                to="ventas.notaventa",
            ),
        ),
        migrations.AlterField(
            model_name="clientesaldofavormovimiento",
            name="nota_aplicada",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="movimientos_saldo_favor_cartera",
                to="ventas.notaventa",
            ),
        ),
    ]
