# inventarios/utils.py

from catalogos.models import Almacen


def get_almacen_default():
    return (
        Almacen.objects.filter(es_activo=True, tipo="FISICO").order_by("id").first()
        or Almacen.objects.filter(es_activo=True).order_by("id").first()
    )
