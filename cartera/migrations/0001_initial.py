# Generated manually for cartera module

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("catalogos", "0020_alter_cliente_options_and_more"),
        ("inventarios", "0024_alter_salidainventario_estado_pago"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PagoCliente",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fecha", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("origen", models.CharField(choices=[("MANUAL", "Manual"), ("AUTO_NOTA", "Automático por nota pagada")], default="MANUAL", max_length=10)),
                ("tipo_aplicacion", models.CharField(choices=[("DIRECTO", "Aplicado a notas específicas"), ("FIFO", "Pago global a notas pendientes"), ("ANTICIPO", "Anticipo / saldo a favor"), ("AUTO", "Pago automático por nota pagada")], default="DIRECTO", max_length=10)),
                ("monto_recibido", models.DecimalField(decimal_places=2, max_digits=14)),
                ("referencia", models.CharField(blank=True, max_length=120)),
                ("observaciones", models.TextField(blank=True)),
                ("estado", models.CharField(choices=[("ACT", "Activo"), ("CAN", "Cancelado")], db_index=True, default="ACT", max_length=3)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("cancelado_en", models.DateTimeField(blank=True, null=True)),
                ("motivo_cancelacion", models.TextField(blank=True)),
                ("cancelado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="pagos_cartera_cancelados", to=settings.AUTH_USER_MODEL)),
                ("cliente", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="pagos_cartera", to="catalogos.cliente")),
                ("creado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="pagos_cartera_creados", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Pago de cliente",
                "verbose_name_plural": "Pagos de clientes",
                "ordering": ["-fecha", "-id"],
                "permissions": [("puede_registrar_pagos", "Puede registrar pagos"), ("puede_cancelar_pagos", "Puede cancelar pagos"), ("puede_devolver_saldo_favor", "Puede devolver saldo a favor"), ("puede_ver_estado_cuenta", "Puede ver estado de cuenta de clientes")],
            },
        ),
        migrations.CreateModel(
            name="PagoMetodoDetalle",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("metodo", models.CharField(choices=[("EFECTIVO", "Efectivo"), ("TRANSFERENCIA", "Transferencia"), ("TARJETA", "Tarjeta"), ("CHEQUE", "Cheque"), ("OTRO", "Otro")], max_length=20)),
                ("monto", models.DecimalField(decimal_places=2, max_digits=14)),
                ("referencia", models.CharField(blank=True, max_length=120)),
                ("pago", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="metodos", to="cartera.pagocliente")),
            ],
            options={"verbose_name": "Método de pago", "verbose_name_plural": "Métodos de pago"},
        ),
        migrations.CreateModel(
            name="PagoAplicacionNota",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("monto_aplicado", models.DecimalField(decimal_places=2, max_digits=14)),
                ("aplicado_en", models.DateTimeField(auto_now_add=True)),
                ("observaciones", models.CharField(blank=True, max_length=255)),
                ("creado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="aplicaciones_cartera_creadas", to=settings.AUTH_USER_MODEL)),
                ("nota_venta", models.ForeignKey(limit_choices_to={"tipo": "VTA"}, on_delete=django.db.models.deletion.PROTECT, related_name="aplicaciones_cartera", to="inventarios.salidainventario")),
                ("pago", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="aplicaciones", to="cartera.pagocliente")),
            ],
            options={"verbose_name": "Aplicación de pago a nota", "verbose_name_plural": "Aplicaciones de pagos a notas", "ordering": ["nota_venta__fecha", "nota_venta__folio", "id"]},
        ),
        migrations.CreateModel(
            name="ClienteSaldoFavorMovimiento",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo", models.CharField(choices=[("GEN", "Generación de saldo a favor"), ("APL", "Aplicación de saldo a favor"), ("DEV", "Devolución de saldo a favor"), ("CAN", "Cancelación / reversa")], max_length=3)),
                ("fecha", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("monto", models.DecimalField(decimal_places=2, max_digits=14)),
                ("metodo_devolucion", models.CharField(blank=True, max_length=20)),
                ("referencia", models.CharField(blank=True, max_length=120)),
                ("observaciones", models.TextField(blank=True)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("autorizado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="saldos_favor_cartera_autorizados", to=settings.AUTH_USER_MODEL)),
                ("cliente", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="movimientos_saldo_favor_cartera", to="catalogos.cliente")),
                ("creado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="saldos_favor_cartera_creados", to=settings.AUTH_USER_MODEL)),
                ("nota_aplicada", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="movimientos_saldo_favor_cartera", to="inventarios.salidainventario")),
                ("pago_origen", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="movimientos_saldo_favor", to="cartera.pagocliente")),
            ],
            options={"verbose_name": "Movimiento de saldo a favor", "verbose_name_plural": "Movimientos de saldo a favor", "ordering": ["-fecha", "-id"]},
        ),
        migrations.AddIndex(model_name="pagocliente", index=models.Index(fields=["cliente", "fecha"], name="cartera_pag_cliente_3ea20a_idx")),
        migrations.AddIndex(model_name="pagocliente", index=models.Index(fields=["estado"], name="cartera_pag_estado_bbd8a4_idx")),
        migrations.AddIndex(model_name="pagocliente", index=models.Index(fields=["tipo_aplicacion"], name="cartera_pag_tipo_ap_26105d_idx")),
        migrations.AddConstraint(model_name="pagocliente", constraint=models.CheckConstraint(condition=models.Q(("monto_recibido__gt", 0)), name="pago_cliente_monto_recibido_gt_0")),
        migrations.AddConstraint(model_name="pagometododetalle", constraint=models.CheckConstraint(condition=models.Q(("monto__gt", 0)), name="pago_metodo_monto_gt_0")),
        migrations.AddIndex(model_name="pagoaplicacionnota", index=models.Index(fields=["nota_venta"], name="cartera_pag_nota_ve_20a596_idx")),
        migrations.AddIndex(model_name="pagoaplicacionnota", index=models.Index(fields=["pago"], name="cartera_pag_pago_id_38a88b_idx")),
        migrations.AddConstraint(model_name="pagoaplicacionnota", constraint=models.CheckConstraint(condition=models.Q(("monto_aplicado__gt", 0)), name="aplicacion_nota_monto_gt_0")),
        migrations.AddIndex(model_name="clientesaldofavormovimiento", index=models.Index(fields=["cliente", "fecha"], name="cartera_cli_cliente_495953_idx")),
        migrations.AddIndex(model_name="clientesaldofavormovimiento", index=models.Index(fields=["tipo"], name="cartera_cli_tipo_5a9e96_idx")),
        migrations.AddConstraint(model_name="clientesaldofavormovimiento", constraint=models.CheckConstraint(condition=models.Q(("monto__gt", 0)), name="saldo_favor_movimiento_monto_gt_0")),
    ]
