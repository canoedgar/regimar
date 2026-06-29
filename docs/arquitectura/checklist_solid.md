# Checklist SOLID para cambios

Usa este checklist antes de crear o modificar codigo de negocio.

## Checklist rapido

- [ ] El cambio tiene una responsabilidad principal clara.
- [ ] La vista solo coordina HTTP, formularios, servicios y respuesta.
- [ ] La regla de negocio vive en `services` o `use_cases`.
- [ ] Las consultas complejas de lectura viven en `selectors`.
- [ ] El modelo no llama servicios de otros dominios.
- [ ] No se agrego una llamada a un metodo privado de otra clase o servicio.
- [ ] No se agrego una dependencia cruzada entre apps sin justificacion.
- [ ] El servicio recibe solo los datos que necesita, no un `request` completo salvo adaptador web.
- [ ] El cambio puede probarse sin depender de una vista completa.
- [ ] La regla nueva tiene prueba o queda registrada la razon de no agregarla.

## Single Responsibility Principle

Preguntas:

- Este archivo tiene una sola razon dominante para cambiar?
- La clase o funcion se puede describir con una frase corta?
- Estoy mezclando validacion, persistencia, notificacion, calculo y presentacion?
- El modulo crecio porque era el lugar correcto o porque era el lugar mas facil?

Alertas:

- Servicios con muchos verbos en el nombre o descripcion.
- Vistas que calculan reglas de negocio.
- Modelos que importan servicios.
- Archivos de vistas con multiples subdominios.

Accion sugerida:

- Extraer servicio pequeno.
- Extraer selector.
- Crear use case si el flujo coordina varias operaciones.

## Open/Closed Principle

Preguntas:

- Agregar una variante nueva obliga a modificar un bloque central?
- Hay condicionales que creceran con nuevas reglas?
- La regla podria modelarse como estrategia?

Alertas:

- `if/elif` por tipo de pago, tipo de cliente, tipo de almacen o tipo de calculo.
- Servicios centrales que se modifican cada vez que aparece una regla nueva.

Accion sugerida:

- Crear estrategia.
- Crear registro de handlers.
- Separar regla variable de orquestacion estable.

## Liskov Substitution Principle

Preguntas:

- Una subclase/proxy puede usarse donde se espera la clase base sin romper expectativas?
- El proxy cambia comportamiento de forma sorpresiva?
- La herencia representa una especializacion real?

Alertas:

- Proxies con managers que filtran datos sin que el consumidor lo entienda.
- Subclases que invalidan contratos de la clase base.

Accion sugerida:

- Documentar el contrato.
- Preferir composicion si la herencia no representa sustitucion real.

## Interface Segregation Principle

Preguntas:

- El servicio recibe dependencias demasiado grandes?
- Estoy pasando `request`, `form`, `model` completo o diccionarios enormes cuando necesito pocos campos?
- El consumidor depende de metodos que no usa?

Alertas:

- Servicios que reciben `request` para obtener solo `user`.
- Diccionarios con muchas claves implicitas.
- Helpers genericos usados por varios dominios sin contrato claro.

Accion sugerida:

- Crear DTO/dataclass.
- Crear contexto reducido.
- Dividir interfaz grande en funciones o protocolos pequenos.

## Dependency Inversion Principle

Preguntas:

- La regla de alto nivel depende directamente de una implementacion concreta?
- Puedo probar el servicio sustituyendo pagos, stock, credito o notificaciones?
- La dependencia cruzada entre apps es estable o deberia pasar por un puerto?

Alertas:

- Imports internos para evitar ciclos.
- `ventas` llamando directamente detalles de `cartera`.
- `catalogos` consultando cartera para reglas de credito.
- Servicios con imports de muchos dominios.

Accion sugerida:

- Crear puerto con `typing.Protocol`.
- Crear adaptador concreto.
- Inyectar dependencia en el use case.

## Checklist antes de terminar un refactor

- [ ] No cambie comportamiento funcional sin prueba o validacion.
- [ ] No reverti cambios ajenos.
- [ ] El flujo principal sigue teniendo una entrada clara.
- [ ] Los nombres reflejan lenguaje de negocio.
- [ ] Las dependencias nuevas son mas simples que las anteriores.
- [ ] La documentacion de arquitectura sigue vigente.

## Criterios para aceptar deuda temporal

Se puede aceptar deuda temporal si:

- El comportamiento queda cubierto por prueba.
- Hay comentario o documento que explique por que es temporal.
- Existe ticket o entrada en `docs/arquitectura/deuda_tecnica_solid.md`.
- La deuda no crea una dependencia circular nueva.
- La deuda no obliga a usar metodos privados desde otros modulos.
