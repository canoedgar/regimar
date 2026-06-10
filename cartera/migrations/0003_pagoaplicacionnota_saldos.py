from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cartera", "0002_rename_cartera_cli_cliente_495953_idx_cartera_cli_cliente_8df3be_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="pagoaplicacionnota",
            name="saldo_antes",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True),
        ),
        migrations.AddField(
            model_name="pagoaplicacionnota",
            name="saldo_despues",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True),
        ),
    ]
