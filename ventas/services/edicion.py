from ventas.services.marcado import marcar_nota_editada
from ventas.use_cases.agregar_productos_nota import AgregarProductosNotaUseCase
from ventas.use_cases.ajustar_precios_nota import AjustarPreciosNotaUseCase
from ventas.use_cases.editar_datos_nota import EditarDatosNotaUseCase


class EditarDatosNotaService:
    def __init__(self, **kwargs):
        self.use_case = EditarDatosNotaUseCase(**kwargs)

    def validar(self):
        return self.use_case.validar()

    def execute(self):
        return self.use_case.execute()


class AjustarPreciosNotaService:
    def __init__(self, **kwargs):
        self.use_case = AjustarPreciosNotaUseCase(**kwargs)

    def validar(self):
        return self.use_case.validar()

    def execute(self):
        return self.use_case.execute()


class AgregarProductosNotaService:
    def __init__(self, **kwargs):
        self.use_case = AgregarProductosNotaUseCase(**kwargs)

    def validar(self):
        return self.use_case.validar()

    def execute(self):
        return self.use_case.execute()
