from django.db import migrations, models


def migrar_logo_salida_a_regimar(apps, schema_editor):
    SalidaInventario = apps.get_model("inventarios", "SalidaInventario")
    SalidaInventario.objects.exclude(logo_nota="REGIMAR").update(logo_nota="REGIMAR")


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("inventarios", "0028_entrada_inventario_xml_defaults"),
    ]

    operations = [
        migrations.RunPython(migrar_logo_salida_a_regimar, noop_reverse),
        migrations.AlterField(
            model_name="salidainventario",
            name="logo_nota",
            field=models.CharField(
                choices=[("REGIMAR", "Regimar")],
                default="REGIMAR",
                help_text="Logo usado históricamente para imprimir esta nota de venta.",
                max_length=20,
                verbose_name="Logo",
            ),
        ),
    ]
