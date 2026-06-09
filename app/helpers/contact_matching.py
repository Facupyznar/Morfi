"""Servicio de matching de contactos → usuarios de Morfi.

Principio de diseño: este servicio es INDEPENDIENTE de la fuente de los
contactos. Recibe una lista de emails (y opcionalmente teléfonos) provenientes
de cualquier origen (Google People API, CSV, pegado manual) y devuelve los
``User`` de Morfi que coinciden. No sabe nada de Google ni de cómo se obtuvo
la lista: esa es la clave para poder sumar otras fuentes sin tocar la lógica
social (sugerencias + solicitudes de amistad vía el módulo Friends).
"""
import re

from sqlalchemy import and_, or_

from app.database import db
from app.models.enums import FriendshipStatus
from app.models.friends import Friends
from app.models.user import Role, User

# Roles que pueden aparecer como sugerencia de amistad (comensales).
MATCHABLE_ROLES = (Role.COMENSAL, Role.ADMIN_GLOBAL)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalizar_emails(emails):
    """Limpia, valida y deduplica una lista de emails (lowercase + trim)."""
    normalizados = []
    vistos = set()
    for email in emails or []:
        if not isinstance(email, str):
            continue
        limpio = email.strip().lower()
        if not limpio or not _EMAIL_RE.match(limpio) or limpio in vistos:
            continue
        vistos.add(limpio)
        normalizados.append(limpio)
    return normalizados


def normalizar_telefono(telefono):
    """Normaliza un teléfono a un formato comparable estilo E.164 (best-effort).

    Sin región de referencia no podemos garantizar E.164 completo, así que
    conservamos un eventual ``+`` inicial y los dígitos. Devuelve None si queda
    demasiado corto para ser un número real.
    """
    if not isinstance(telefono, str):
        return None
    crudo = telefono.strip()
    tiene_mas = crudo.startswith("+")
    digitos = re.sub(r"\D", "", crudo)
    if len(digitos) < 7:
        return None
    return ("+" + digitos) if tiene_mas else digitos


def normalizar_telefonos(telefonos):
    normalizados = []
    vistos = set()
    for telefono in telefonos or []:
        norm = normalizar_telefono(telefono)
        if norm and norm not in vistos:
            vistos.add(norm)
            normalizados.append(norm)
    return normalizados


def _ids_relaciones_existentes(user_id):
    """IDs de usuarios que ya son amigos / tienen solicitud pendiente / bloqueo.

    Replica la lógica del módulo Friends de forma local para no acoplar este
    servicio a las rutas. Estos se excluyen de las sugerencias.
    """
    relaciones = (
        db.session.query(Friends.user_id_1, Friends.user_id_2)
        .filter(
            or_(Friends.user_id_1 == user_id, Friends.user_id_2 == user_id),
            Friends.estado.in_(
                [
                    FriendshipStatus.PENDIENTE,
                    FriendshipStatus.ACEPTADA,
                    FriendshipStatus.BLOQUEADA,
                ]
            ),
        )
        .all()
    )
    ids = set()
    for user_id_1, user_id_2 in relaciones:
        ids.add(user_id_1)
        ids.add(user_id_2)
    ids.discard(user_id)
    return ids


def encontrar_usuarios_por_contactos(emails, telefonos=None, excluir_user_id=None):
    """Devuelve los ``User`` de Morfi que coinciden con la agenda recibida.

    Reglas:
    - Matchea por email (y por teléfono si el modelo lo soportara — hoy User no
      tiene columna de teléfono, así que ``telefonos`` se normaliza pero no se usa).
    - Excluye al propio usuario (``excluir_user_id``).
    - Excluye a quienes tengan ``discoverable_by_contacts == False``.
    - Excluye a quienes ya sean amigos o tengan solicitud pendiente/bloqueo.
    - Solo considera comensales activos.
    """
    emails_norm = normalizar_emails(emails)
    normalizar_telefonos(telefonos)  # normalizado para forward-compat; User no tiene teléfono aún

    if not emails_norm:
        return []

    condiciones = [User.email.in_(emails_norm)]
    # Cuando User tenga columna de teléfono, sumar aquí: User.telefono.in_(telefonos_norm)

    query = (
        db.session.query(User)
        .filter(
            or_(*condiciones),
            User.is_active.is_(True),
            User.rol.in_(MATCHABLE_ROLES),
            User.discoverable_by_contacts.is_(True),
        )
    )

    if excluir_user_id is not None:
        query = query.filter(User.user_id != excluir_user_id)
        excluidos = _ids_relaciones_existentes(excluir_user_id)
        if excluidos:
            query = query.filter(User.user_id.notin_(excluidos))

    return query.all()
