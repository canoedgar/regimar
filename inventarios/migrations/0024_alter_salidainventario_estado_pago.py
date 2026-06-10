# Generated manually for cartera payment status support

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventarios", "0023_salidainventario_editada_en_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="salidainventario",
            name="estado_pago",
            field=models.CharField(
                choices=[
                    ("PAG", "Pagado"),
                    ("PEND", "Pendiente de pago"),
                    ("PARC", "Pago parcial"),
                ],
                db_index=True,
                default="PEND",
                help_text="Estado administrativo de pago de la nota; no depende de la forma de pago.",
                max_length=4,
                verbose_name="Estado de pago",
            ),
        ),
    ]
