from django.db import migrations, models


def migrar_logo_nota_a_regimar(apps, schema_editor):
    NotaVenta = apps.get_model("ventas", "NotaVenta")
    NotaVenta.objects.exclude(logo_nota="REGIMAR").update(logo_nota="REGIMAR")


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("ventas", "0002_notaventa_fisica"),
        ("inventarios", "0029_logo_nota_regimar_unico"),
        ("catalogos", "0028_logo_regimar_unico"),
    ]

    operations = [
        migrations.RunPython(migrar_logo_nota_a_regimar, noop_reverse),
        migrations.AlterField(
            model_name="notaventa",
            name="logo_nota",
            field=models.CharField(
                choices=[("REGIMAR", "Regimar")],
                default="REGIMAR",
                max_length=20,
                verbose_name="Logo",
            ),
        ),
    ]
