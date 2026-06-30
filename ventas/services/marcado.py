from django.utils import timezone


def marcar_nota_editada(salida, user=None):
    salida.editada_en = timezone.now()
    salida.editada_por = user if getattr(user, "is_authenticated", False) else None
    salida.save(update_fields=["editada_en", "editada_por"])
