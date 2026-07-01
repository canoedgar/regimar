from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def migrar_notas_venta(apps, schema_editor):
    SalidaInventario = apps.get_model("inventarios", "SalidaInventario")
    NotaVenta = apps.get_model("ventas", "NotaVenta")
    for salida in SalidaInventario.objects.filter(tipo="VTA"):
        NotaVenta.objects.update_or_create(
            salida_id=salida.id,
            defaults={
                "folio": salida.folio,
                "fecha": salida.fecha,
                "cliente": salida.cliente,
                "cliente_ref_id": salida.cliente_ref_id,
                "forma_pago_venta": salida.forma_pago_venta,
                "estado_pago": salida.estado_pago,
                "comision_terminal_porcentaje": salida.comision_terminal_porcentaje,
                "comision_terminal_monto": salida.comision_terminal_monto,
                "cliente_direccion": salida.cliente_direccion,
                "cliente_contacto": salida.cliente_contacto,
                "logo_nota": salida.logo_nota,
                "documento_referencia": salida.documento_referencia,
                "motivo": salida.motivo,
                "observaciones": salida.observaciones,
                "estado": salida.estado,
                "cancelada_en": salida.cancelada_en,
                "motivo_cancelacion": salida.motivo_cancelacion,
                "editada_en": salida.editada_en,
                "editada_por_id": salida.editada_por_id,
            },
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("ventas", "0001_initial"),
        ("cartera", "0004_relaciones_ventas"),
        ("catalogos", "0024_credito_autorizacion_ventas"),
        ("inventarios", "0028_entrada_inventario_xml_defaults"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.DeleteModel(name="NotaVenta"),
        migrations.CreateModel(
            name="NotaVenta",
            fields=[
                ("salida", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, primary_key=True, related_name="nota_venta", serialize=False, to="inventarios.salidainventario")),
                ("folio", models.CharField(max_length=20, unique=True, verbose_name="Folio")),
                ("fecha", models.DateField(default=django.utils.timezone.now, verbose_name="Fecha")),
                ("cliente", models.CharField(blank=True, max_length=200, verbose_name="Cliente")),
                ("forma_pago_venta", models.CharField(choices=[("CONTADO", "Contado"), ("CREDITO", "Credito"), ("TERMINAL", "Terminal bancaria")], default="CONTADO", max_length=10, verbose_name="Forma de pago de venta")),
                ("estado_pago", models.CharField(choices=[("PAG", "Pagado"), ("PEND", "Pendiente de pago"), ("PARC", "Pago parcial")], db_index=True, default="PEND", max_length=4, verbose_name="Estado de pago")),
                ("comision_terminal_porcentaje", models.DecimalField(decimal_places=4, default=0, max_digits=7, verbose_name="Comision terminal (%)")),
                ("comision_terminal_monto", models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name="Comision terminal")),
                ("cliente_direccion", models.TextField(blank=True, verbose_name="Direccion del cliente para esta venta")),
                ("cliente_contacto", models.CharField(blank=True, max_length=200, verbose_name="Contacto del cliente para esta venta")),
                ("logo_nota", models.CharField(choices=[("REGIMAR", "Regimar")], default="REGIMAR", max_length=20, verbose_name="Logo")),
                ("documento_referencia", models.CharField(blank=True, max_length=60, verbose_name="Documento referencia")),
                ("motivo", models.TextField(blank=True, verbose_name="Motivo")),
                ("observaciones", models.TextField(blank=True, verbose_name="Observaciones")),
                ("estado", models.CharField(choices=[("ACT", "Activa"), ("CAN", "Cancelada")], db_index=True, default="ACT", max_length=3, verbose_name="Estado")),
                ("cancelada_en", models.DateTimeField(blank=True, null=True, verbose_name="Cancelada en")),
                ("motivo_cancelacion", models.TextField(blank=True, verbose_name="Motivo de cancelacion")),
                ("editada_en", models.DateTimeField(blank=True, null=True, verbose_name="Editada en")),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("cliente_ref", models.ForeignKey(blank=True, help_text="Cliente del catalogo usado para historial de precios.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="notas_venta", to="catalogos.cliente")),
                ("editada_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="notas_venta_comerciales_editadas", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Nota de venta",
                "verbose_name_plural": "Notas de venta",
                "ordering": ["-fecha", "-folio"],
            },
        ),
        migrations.RunPython(migrar_notas_venta, noop_reverse),
    ]
