from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from notificaciones.forms import separar_destinatarios
from notificaciones.services.reportes import enviar_reporte_general_por_correo, rango_por_dias


class Command(BaseCommand):
    help = "Envía por correo el reporte general de inventarios, ventas y cartera."

    def add_arguments(self, parser):
        parser.add_argument("--desde", dest="desde", help="Fecha inicial en formato YYYY-MM-DD.")
        parser.add_argument("--hasta", dest="hasta", help="Fecha final en formato YYYY-MM-DD.")
        parser.add_argument("--dias", dest="dias", type=int, default=0, help="Rango relativo: 0=hoy, 1=ayer, 7=últimos 7 días cerrados.")
        parser.add_argument("--destinatarios", dest="destinatarios", help="Correos separados por coma, punto y coma o salto de línea.")

    def handle(self, *args, **options):
        if options.get("desde") or options.get("hasta"):
            if not options.get("desde") or not options.get("hasta"):
                raise CommandError("Usa --desde y --hasta juntos en formato YYYY-MM-DD.")
            try:
                fecha_inicio = datetime.strptime(options["desde"], "%Y-%m-%d").date()
                fecha_fin = datetime.strptime(options["hasta"], "%Y-%m-%d").date()
            except ValueError as exc:
                raise CommandError("Las fechas deben tener formato YYYY-MM-DD.") from exc
            if fecha_inicio > fecha_fin:
                raise CommandError("La fecha inicial no puede ser mayor que la fecha final.")
        else:
            fecha_inicio, fecha_fin = rango_por_dias(options.get("dias") or 0)

        destinatarios = separar_destinatarios(options.get("destinatarios") or "")
        if not destinatarios:
            destinatarios = getattr(settings, "NOTIFICACIONES_REPORTES_DESTINATARIOS", [])
        if not destinatarios:
            raise CommandError(
                "No hay destinatarios. Define NOTIFICACIONES_REPORTES_DESTINATARIOS en .env "
                "o usa --destinatarios correo@empresa.com."
            )

        registro = enviar_reporte_general_por_correo(
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            destinatarios=destinatarios,
        )
        self.stdout.write(self.style.SUCCESS(f"Reporte enviado. Bitácora #{registro.id}"))
