
from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('catalogos', '0013_alter_almacen_tipo_costo'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProductoMetricaConversion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(help_text='Nombre visible de la presentación. Ejemplo: Caja 10 kgs.', max_length=100)),
                ('nombre_normalizado', models.CharField(editable=False, max_length=120)),
                ('unidad_origen', models.CharField(help_text='Unidad o presentación que venderá el usuario. Ejemplo: Caja.', max_length=30)),
                ('cantidad_origen', models.DecimalField(decimal_places=4, default=Decimal('1'), help_text='Cantidad base de la unidad origen. Normalmente 1.', max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal('0.0001'))])),
                ('factor_conversion', models.DecimalField(decimal_places=4, help_text='Cuánto equivale la cantidad origen en la métrica default del producto.', max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal('0.0001'))])),
                ('activo', models.BooleanField(default=True)),
                ('fecha_alta', models.DateTimeField(auto_now_add=True)),
                ('producto', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='conversiones_metricas', to='catalogos.producto')),
            ],
            options={
                'verbose_name': 'Conversión de métrica',
                'verbose_name_plural': 'Conversiones de métricas',
                'ordering': ['producto__nombre', 'nombre'],
            },
        ),
        migrations.AddConstraint(
            model_name='productometricaconversion',
            constraint=models.UniqueConstraint(fields=('producto', 'nombre_normalizado'), name='uq_producto_conversion_nombre_normalizado'),
        ),
    ]
