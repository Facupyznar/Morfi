"""Servicio de recomendación de amigos por afinidad.

Desacoplado (igual que el matching de contactos): recibe el usuario actual y
devuelve una lista de sugerencias rankeadas con un motivo legible. La ruta solo
orquesta; nada de scoring en la vista.

Señales combinadas (pesos como constantes, ajustables):
  - Tags culinarios compartidos (UserTags)      → peso ALTO
  - Amigos en común aceptados (Friends)         → peso ALTO
  - Restaurantes favoritos compartidos          → peso MEDIO
  - Cercanía geográfica (haversine)             → peso BAJO / desempate

Un candidato solo se incluye si tiene al menos UNA señal "fuerte" (tags, amigos
o favoritos en común). La cercanía suma como bonus/desempate pero por sí sola no
califica: no queremos rellenar con gente sin nada en común.
"""
from collections import defaultdict

from sqlalchemy import func, or_

from app.database import db
from app.helpers.contact_matching import MATCHABLE_ROLES
from app.location import haversine_km
from app.models.enums import FriendshipStatus
from app.models.friends import Friends
from app.models.user import User
from app.models.user_favorites import UserFavorites
from app.models.user_tags import UserTags

# ── Pesos de scoring (ajustables) ──────────────────────────────────
PESO_TAG_COMPARTIDO = 10       # por cada tag culinario en común (ALTO)
PESO_AMIGO_COMUN = 12          # por cada amigo en común aceptado (ALTO)
PESO_FAVORITO_COMPARTIDO = 6   # por cada restaurante favorito en común (MEDIO)
BONUS_CERCANIA = 5             # bonus único si están cerca (BAJO / desempate)
RADIO_CERCANIA_KM = 5.0        # "misma zona"


def _tag_ids_de(user_id):
    filas = db.session.query(UserTags.id_tag).filter(UserTags.user_id == user_id).all()
    return {fila[0] for fila in filas}


def _favorito_ids_de(user_id):
    filas = (
        db.session.query(UserFavorites.id_restaurante)
        .filter(UserFavorites.user_id == user_id)
        .all()
    )
    return {fila[0] for fila in filas}


def _amigos_aceptados_de(user_id):
    filas = (
        db.session.query(Friends.user_id_1, Friends.user_id_2)
        .filter(
            Friends.estado == FriendshipStatus.ACEPTADA,
            or_(Friends.user_id_1 == user_id, Friends.user_id_2 == user_id),
        )
        .all()
    )
    amigos = set()
    for uid1, uid2 in filas:
        amigos.add(uid1)
        amigos.add(uid2)
    amigos.discard(user_id)
    return amigos


def _ids_relaciones_existentes(user_id):
    """Amigos / pendientes / bloqueados: se excluyen de las sugerencias."""
    filas = (
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
    for uid1, uid2 in filas:
        ids.add(uid1)
        ids.add(uid2)
    ids.discard(user_id)
    return ids


def _conteo_compartido(tabla_col_user, tabla_col_item, valores, excluidos):
    """Cuenta items compartidos por usuario candidato (query agregada, sin N+1)."""
    if not valores:
        return {}
    filas = (
        db.session.query(tabla_col_user, func.count().label("n"))
        .filter(tabla_col_item.in_(valores), tabla_col_user.notin_(excluidos))
        .group_by(tabla_col_user)
        .all()
    )
    return {uid: n for uid, n in filas}


def _amigos_comunes_por_candidato(amigos_actual, excluidos, user_id):
    """Para cada candidato, cuántos de MIS amigos aceptados también son SUS amigos.

    Una sola query sobre Friends (amistades aceptadas que tocan a mis amigos);
    el otro extremo de cada amistad es el candidato. Evita N+1.
    """
    if not amigos_actual:
        return {}
    filas = (
        db.session.query(Friends.user_id_1, Friends.user_id_2)
        .filter(
            Friends.estado == FriendshipStatus.ACEPTADA,
            or_(
                Friends.user_id_1.in_(amigos_actual),
                Friends.user_id_2.in_(amigos_actual),
            ),
        )
        .all()
    )
    conteo = defaultdict(int)
    for uid1, uid2 in filas:
        if uid1 in amigos_actual and uid2 not in amigos_actual:
            candidato = uid2
        elif uid2 in amigos_actual and uid1 not in amigos_actual:
            candidato = uid1
        else:
            continue
        if candidato == user_id or candidato in excluidos:
            continue
        conteo[candidato] += 1
    return dict(conteo)


def _iniciales(nombre):
    partes = [p for p in (nombre or "").split() if p]
    if len(partes) >= 2:
        return f"{partes[0][0]}{partes[1][0]}".upper()
    return (nombre[:2].upper() if nombre else "US") or "US"


def _motivo(n_tags, n_amigos, n_favs, cerca):
    """Arma un motivo legible priorizando la señal más fuerte (hasta 2 razones)."""
    razones = []
    if n_tags:
        razones.append(f"{n_tags} gusto{'s' if n_tags > 1 else ''} en común")
    if n_amigos:
        razones.append(f"{n_amigos} amigo{'s' if n_amigos > 1 else ''} en común")
    if n_favs:
        if n_favs > 1:
            razones.append(f"{n_favs} lugares favoritos en común")
        else:
            razones.append("Les gusta el mismo lugar")
    if not razones and cerca:
        razones.append("Cerca tuyo")
    elif cerca and len(razones) < 2:
        razones.append("Cerca tuyo")
    return " · ".join(razones[:2])


def sugerir_usuarios_por_afinidad(usuario_actual, excluir_ids=None, limit=20):
    """Devuelve sugerencias rankeadas: [{user, id, name, ..., motivo, score}]."""
    user_id = usuario_actual.user_id

    mis_tags = _tag_ids_de(user_id)
    mis_favs = _favorito_ids_de(user_id)
    mis_amigos = _amigos_aceptados_de(user_id)

    excluidos = _ids_relaciones_existentes(user_id)
    excluidos.add(user_id)
    if excluir_ids:
        for raw in excluir_ids:
            # Acepta UUID o str (los IDs de "De tu agenda" llegan como str).
            try:
                from uuid import UUID as _UUID
                excluidos.add(raw if not isinstance(raw, str) else _UUID(raw))
            except (ValueError, AttributeError):
                continue

    # Conteos agregados (3 queries) — sin N+1.
    tags_compartidos = _conteo_compartido(UserTags.user_id, UserTags.id_tag, mis_tags, excluidos)
    favs_compartidos = _conteo_compartido(
        UserFavorites.user_id, UserFavorites.id_restaurante, mis_favs, excluidos
    )
    amigos_comunes = _amigos_comunes_por_candidato(mis_amigos, excluidos, user_id)

    candidatos = set(tags_compartidos) | set(favs_compartidos) | set(amigos_comunes)
    if not candidatos:
        return []

    # Una sola query para traer los User candidatos (datos + lat/lon).
    usuarios = (
        db.session.query(User)
        .filter(
            User.user_id.in_(candidatos),
            User.is_active.is_(True),
            User.rol.in_(MATCHABLE_ROLES),
        )
        .all()
    )

    tengo_ubicacion = usuario_actual.latitude is not None and usuario_actual.longitude is not None

    sugerencias = []
    for u in usuarios:
        n_tags = tags_compartidos.get(u.user_id, 0)
        n_amigos = amigos_comunes.get(u.user_id, 0)
        n_favs = favs_compartidos.get(u.user_id, 0)

        # Señal fuerte requerida: cercanía sola no califica.
        if not (n_tags or n_amigos or n_favs):
            continue

        cerca = False
        if tengo_ubicacion and u.latitude is not None and u.longitude is not None:
            distancia = haversine_km(
                usuario_actual.latitude, usuario_actual.longitude, u.latitude, u.longitude
            )
            cerca = distancia <= RADIO_CERCANIA_KM

        score = (
            n_tags * PESO_TAG_COMPARTIDO
            + n_amigos * PESO_AMIGO_COMUN
            + n_favs * PESO_FAVORITO_COMPARTIDO
            + (BONUS_CERCANIA if cerca else 0)
        )

        sugerencias.append(
            {
                "user": u,
                "id": str(u.user_id),
                "name": getattr(u, "name", None) or u.username,
                "username": u.username,
                "initials": _iniciales(getattr(u, "name", None) or u.username),
                "photo_url": getattr(u, "foto_perfil", None),
                "avatar_url": getattr(u, "avatar_url", None),
                "motivo": _motivo(n_tags, n_amigos, n_favs, cerca),
                "score": score,
            }
        )

    sugerencias.sort(key=lambda s: s["score"], reverse=True)
    return sugerencias[:limit]
