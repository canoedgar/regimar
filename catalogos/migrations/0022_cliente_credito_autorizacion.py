# Generated manually for crédito de clientes y autorizaciones extraordinarias

import django.core.validators
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('inventarios', '0026_traspasos_inventario'),
        ('catalogos', '0021_cliente_logo'),
    ]

    operations = [
        migrations.AddField(
            model_name='cliente',
            name='limite_credito',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Monto máximo autorizado de cartera. 0 = sin validación por monto.', max_digits=14, validators=[django.core.validators.MinValueValidator(Decimal('0.00'))], verbose_name='Límite de crédito'),
        ),
        migrations.AddField(
            model_name='cliente',
            name='dias_credito',
            field=models.PositiveIntegerField(default=0, help_text='Días máximos permitidos para notas pendientes. 0 = sin validación por días.', verbose_name='Días de crédito'),
        ),
        migrations.CreateModel(
            name='ClienteCreditoAutorizacion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token', models.CharField(db_index=True, editable=False, max_length=96, unique=True)),
                ('fecha_solicitud', models.DateField(db_index=True, default=django.utils.timezone.localdate)),
                ('total_venta', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=14)),
                ('saldo_actual', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=14)),
                ('saldo_proyectado', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=14)),
                ('limite_credito', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=14)),
                ('dias_credito', models.PositiveIntegerField(default=0)),
                ('motivo', models.TextField(blank=True)),
                ('estado', models.CharField(choices=[('PEND', 'Pendiente'), ('APR', 'Aprobada'), ('RECH', 'Rechazada')], db_index=True, default='PEND', max_length=4)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('respondido_en', models.DateTimeField(blank=True, null=True)),
                ('usado_en', models.DateTimeField(blank=True, null=True)),
                ('comentario_resolucion', models.TextField(blank=True)),
                ('cliente', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='autorizaciones_credito', to='catalogos.cliente')),
                ('usuario_solicita', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='solicitudes_credito_extraordinario', to=settings.AUTH_USER_MODEL)),
                ('venta_autorizada', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='autorizaciones_credito_usadas', to='inventarios.salidainventario')),
            ],
            options={
                'verbose_name': 'Autorización de venta extraordinaria',
                'verbose_name_plural': 'Autorizaciones de ventas extraordinarias',
                'ordering': ['-creado_en', '-id'],
                'indexes': [models.Index(fields=['cliente', 'fecha_solicitud', 'estado'], name='catalogos_c_cliente_e4cb8c_idx'), models.Index(fields=['fecha_solicitud', 'estado'], name='catalogos_c_fecha_s_7696c0_idx')],
            },
        ),
    ]
