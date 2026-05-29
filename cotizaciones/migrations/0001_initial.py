# Generated manually for cotizaciones first version

import django.core.validators
import django.db.models.deletion
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("catalogos", "0020_alter_cliente_options_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="CotizacionPrecio",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("folio", models.CharField(db_index=True, max_length=30, unique=True)),
                ("prospecto_nombre", models.CharField(blank=True, max_length=180)),
                ("prospecto_contacto", models.CharField(blank=True, max_length=150)),
                ("prospecto_telefono", models.CharField(blank=True, max_length=30)),
                ("prospecto_email", models.EmailField(blank=True, max_length=254)),
                ("prospecto_direccion", models.TextField(blank=True)),
                ("fecha", models.DateField(auto_now_add=True)),
                ("fecha_vigencia", models.DateField()),
                ("estatus", models.CharField(choices=[("BORRADOR", "Borrador"), ("ENVIADA", "Enviada"), ("AUTORIZADA", "Autorizada"), ("RECHAZADA", "Rechazada"), ("VENCIDA", "Vencida"), ("CANCELADA", "Cancelada")], default="BORRADOR", max_length=20)),
                ("observaciones", models.TextField(blank=True)),
                ("fecha_autorizacion", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("autorizado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="cotizaciones_precio_autorizadas", to=settings.AUTH_USER_MODEL)),
                ("cliente", models.ForeignKey(blank=True, help_text="Cliente existente. Si es prospecto, puede dejarse vacío.", null=True, on_delete=django.db.models.deletion.PROTECT, related_name="cotizaciones_precio", to="catalogos.cliente")),
                ("creado_por", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="cotizaciones_precio_creadas", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Cotización de precios",
                "verbose_name_plural": "Cotizaciones de precios",
                "ordering": ["-fecha", "-id"],
            },
        ),
        migrations.CreateModel(
            name="CotizacionPrecioDetalle",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("costo_base", models.DecimalField(decimal_places=2, default=0, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))])),
                ("precio_sugerido", models.DecimalField(decimal_places=2, default=0, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))])),
                ("precio_minimo", models.DecimalField(decimal_places=2, default=0, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))])),
                ("precio_propuesto", models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))])),
                ("margen_porcentaje", models.DecimalField(decimal_places=2, default=0, max_digits=8)),
                ("utilidad_unitaria", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("unidad_precio", models.CharField(default="KG", max_length=20)),
                ("requiere_autorizacion", models.BooleanField(default=False)),
                ("autorizado", models.BooleanField(default=False)),
                ("observaciones", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("cotizacion", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="detalles", to="cotizaciones.cotizacionprecio")),
                ("producto", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="cotizaciones_precio_detalle", to="catalogos.producto")),
            ],
            options={
                "verbose_name": "Detalle de cotización de precios",
                "verbose_name_plural": "Detalles de cotización de precios",
                "ordering": ["producto__nombre"],
                "unique_together": {("cotizacion", "producto")},
            },
        ),
    ]
