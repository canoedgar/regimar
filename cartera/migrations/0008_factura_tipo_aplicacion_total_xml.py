from decimal import Decimal

from django.db import migrations, models


def copiar_total_xml(apps, schema_editor):
    FacturaCliente = apps.get_model("cartera", "FacturaCliente")
    for factura in FacturaCliente.objects.all().only("id", "total"):
        FacturaCliente.objects.filter(pk=factura.pk).update(total_xml=factura.total or Decimal("0.00"))


class Migration(migrations.Migration):

    dependencies = [
        ("cartera", "0007_facturacliente_facturaaplicacionnota_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="facturacliente",
            name="tipo_aplicacion",
            field=models.CharField(
                choices=[("GLOBAL", "Global al cliente"), ("NOTAS", "Aplicada a notas")],
                db_index=True,
                default="GLOBAL",
                help_text="Define si la factura queda global al cliente o relacionada a notas específicas.",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="facturacliente",
            name="total_xml",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="Total leído del XML. El total operativo puede capturarse manualmente sin alterar el archivo.",
                max_digits=14,
            ),
        ),
        migrations.RunPython(copiar_total_xml, migrations.RunPython.noop),
        migrations.AddIndex(
            model_name="facturacliente",
            index=models.Index(fields=["tipo_aplicacion"], name="cartera_fac_tipo_ap_b7a1e5_idx"),
        ),
    ]
