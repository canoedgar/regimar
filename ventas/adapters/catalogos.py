from catalogos.services.clientes_precios import registrar_ultimo_precio_cliente


class CatalogosPrecioClienteAdapter:
    def registrar_ultimo_precio(self, *, cliente, producto, precio, usuario=None, observaciones="") -> None:
        registrar_ultimo_precio_cliente(
            cliente=cliente,
            producto=producto,
            precio=precio,
            usuario=usuario,
            observaciones=observaciones,
        )

