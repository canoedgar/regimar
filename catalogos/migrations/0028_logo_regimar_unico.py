from django.db import migrations, models


def migrar_logo_cliente_a_regimar(apps, schema_editor):
    Cliente = apps.get_model("catalogos", "Cliente")
    Cliente.objects.exclude(logo="REGIMAR").update(logo="REGIMAR")


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("catalogos", "0027_notaventa_fisica_fk"),
    ]

    operations = [
        migrations.RunPython(migrar_logo_cliente_a_regimar, noop_reverse),
        migrations.AlterField(
            model_name="cliente",
            name="logo",
            field=models.CharField(
                choices=[("REGIMAR", "Regimar")],
                default="REGIMAR",
                help_text="Logo default que se usará en las notas de venta del cliente.",
                max_length=20,
                verbose_name="Logo",
            ),
        ),
    ]
