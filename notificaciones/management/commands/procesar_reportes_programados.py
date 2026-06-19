from django.core.management.base import BaseCommand
from django.utils import timezone

from notificaciones.forms import separar_destinatarios
from notificaciones.models import ReporteProgramado
from notificaciones.services.reportes import enviar_reporte_general_por_correo, rango_por_dias


class Command(BaseCommand):
    help = "Procesa los reportes programados activos que estén pendientes de envío."

    def add_arguments(self, parser):
        parser.add_argument("--forzar", action="store_true", help="Envía todos los reportes activos sin validar hora ni último envío.")

    def handle(self, *args, **options):
        ahora = timezone.localtime()
        enviados = 0
        omitidos = 0

        for programacion in ReporteProgramado.objects.filter(activo=True):
            ya_enviado_hoy = programacion.ultimo_envio and timezone.localtime(programacion.ultimo_envio).date() == ahora.date()
            hora_pendiente = ahora.time() >= programacion.hora_envio

            if not options["forzar"] and (ya_enviado_hoy or not hora_pendiente):
                omitidos += 1
                continue

            destinatarios = separar_destinatarios(programacion.destinatarios)
            if not destinatarios:
                self.stderr.write(f"{programacion.nombre}: omitido porque no tiene destinatarios.")
                omitidos += 1
                continue

            fecha_inicio, fecha_fin = rango_por_dias(programacion.dias_a_reportar)
            enviar_reporte_general_por_correo(
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                destinatarios=destinatarios,
            )
            programacion.ultimo_envio = timezone.now()
            programacion.save(update_fields=["ultimo_envio", "actualizado_en"])
            enviados += 1
            self.stdout.write(f"Enviado: {programacion.nombre}")

        self.stdout.write(self.style.SUCCESS(f"Reportes enviados: {enviados}. Omitidos: {omitidos}."))
