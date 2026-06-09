"""Helpers de ofertas y beneficios para el lado del comensal.

Centraliza el cálculo de vigencia de ofertas y el progreso de visitas de un
comensal frente a los beneficios de fidelidad de un restaurante.
"""

from datetime import datetime, timezone

from sqlalchemy import func

from app.database import db
from app.models.beneficio import Beneficio
from app.models.enums import BeneficioValorTipo, ReservaStatus
from app.models.oferta import Oferta
from app.models.reserva import Reserva


def contar_visitas_completadas(user_id, restaurant_id) -> int:
    """Cuenta las reservas en estado COMPLETADA de un comensal en un restaurante.

    Es la cantidad de "visitas" reales usada para evaluar los beneficios.
    """
    total = (
        db.session.query(func.count(Reserva.id_reserva))
        .filter(
            Reserva.user_id == user_id,
            Reserva.id_restaurant == restaurant_id,
            Reserva.estado_reserva == ReservaStatus.COMPLETADA,
        )
        .scalar()
    )
    return int(total or 0)


def _as_utc(dt):
    """Normaliza un datetime a UTC-aware para comparaciones consistentes."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def oferta_esta_vigente(oferta, now=None) -> bool:
    """True si la oferta está activa y la fecha actual cae dentro de su rango."""
    if not oferta.activo:
        return False
    now = now or datetime.now(timezone.utc)
    inicio = _as_utc(oferta.fecha_inicio)
    fin = _as_utc(oferta.fecha_fin)
    return (inicio is None or inicio <= now) and (fin is None or now <= fin)


def oferta_payload(oferta) -> dict:
    """Construye el dict que consumen los templates (incluye ISO para el countdown)."""
    fin = _as_utc(oferta.fecha_fin)
    inicio = _as_utc(oferta.fecha_inicio)
    return {
        "id": str(oferta.id),
        "titulo": oferta.titulo,
        "descripcion": oferta.descripcion or "",
        "imagen_path": oferta.imagen_path,
        "fecha_fin_iso": fin.isoformat() if fin else "",
        "fecha_inicio_label": inicio.strftime("%d/%m/%Y") if inicio else "",
        "fecha_fin_label": fin.strftime("%d/%m/%Y %H:%M") if fin else "",
    }


def ofertas_vigentes(restaurant_id) -> list:
    """Devuelve ofertas activas (vigentes + próximas) de un restaurante."""
    now = datetime.now(timezone.utc)
    ofertas = (
        db.session.query(Oferta)
        .filter(Oferta.id_restaurante == restaurant_id, Oferta.activo.is_(True))
        .order_by(Oferta.fecha_fin.asc())
        .all()
    )
    result = []
    for o in ofertas:
        fin = _as_utc(o.fecha_fin)
        # Excluir solo las ya vencidas; incluir vigentes y próximas
        if fin is None or fin > now:
            payload = oferta_payload(o)
            payload["proxima"] = not oferta_esta_vigente(o, now)
            result.append(payload)
    return result


def _valor_label(beneficio) -> str:
    valor = beneficio.valor_beneficio or 0
    if beneficio.tipo_beneficio == BeneficioValorTipo.PORCENTAJE:
        return f"{valor:g}% de descuento"
    return f"${valor:g} de descuento"


def beneficios_con_progreso(restaurant_id, user_id) -> list:
    """Beneficios activos de un restaurante con el progreso de visitas del comensal."""
    beneficios = (
        db.session.query(Beneficio)
        .filter(Beneficio.id_restaurante == restaurant_id, Beneficio.activo.is_(True))
        .order_by(Beneficio.valor_condicion.asc())
        .all()
    )
    if not beneficios:
        return []

    visitas = contar_visitas_completadas(user_id, restaurant_id)
    payload = []
    for beneficio in beneficios:
        objetivo = beneficio.valor_condicion or 0
        progreso = min(visitas, objetivo) if objetivo else visitas
        porcentaje = int(round(progreso / objetivo * 100)) if objetivo else 100
        payload.append(
            {
                "id": str(beneficio.id),
                "descripcion": beneficio.descripcion,
                "valor_label": _valor_label(beneficio),
                "objetivo": objetivo,
                "visitas": visitas,
                "restantes": max(objetivo - visitas, 0),
                "porcentaje": min(porcentaje, 100),
                "desbloqueado": visitas >= objetivo,
            }
        )
    return payload