# Generated manually for the ventas bounded context bootstrap.
from django.db import migrations


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("inventarios", "0026_traspasos_inventario"),
    ]

    operations = [
        migrations.CreateModel(
            name="NotaVenta",
            fields=[],
            options={
                "verbose_name": "Nota de venta",
                "verbose_name_plural": "Notas de venta",
                "proxy": True,
            },
            bases=("inventarios.salidainventario",),
        ),
        migrations.CreateModel(
            name="NotaVentaDetalle",
            fields=[],
            options={
                "verbose_name": "Detalle de nota de venta",
                "verbose_name_plural": "Detalles de notas de venta",
                "proxy": True,
            },
            bases=("inventarios.salidainventariodetalle",),
        ),
    ]
