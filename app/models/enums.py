import enum


class RestaurantStatus(enum.Enum):
    ACTIVO = "activo"
    INACTIVO = "inactivo"
    SUSPENDIDO = "suspendido"


class ReservaStatus(enum.Enum):
    PENDIENTE = "pendiente"
    CONFIRMADA = "confirmada"
    CANCELADA = "cancelada"
    COMPLETADA = "completada"


class TagCategory(enum.Enum):
    COMIDA = "comida"
    AMBIENTE = "ambiente"
    DIETA = "dieta"
    OCASION = "ocasion"
    OTRO = "otro"


class BeneficioTipo(enum.Enum):
    DESCUENTO = "descuento"
    PORCENTAJE = "porcentaje"
    PROMOCION = "promocion"
    REGALO = "regalo"


class BeneficioAplicaA(enum.Enum):
    PLATO = "plato"
    MENU = "menu"
    RESTAURANT = "restaurant"


class FriendshipStatus(enum.Enum):
    PENDIENTE = "pendiente"
    ACEPTADA = "aceptada"
    RECHAZADA = "rechazada"
    BLOQUEADA = "bloqueada"
