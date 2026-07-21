from datetime import datetime, timezone, timedelta
import os
import uuid

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import joinedload

from flask import current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required, logout_user
from werkzeug.utils import secure_filename

from app.models.pago import Pago
from app.models.user_favorites import UserFavorites
from app.models.wishlist import Wishlist
from app.models.wishlist_item import WishlistItem
from app.models.restaurant import Restaurant
from app.database import db
from app.location import resolve_location_payload
from app.models.enums import TagCategory
from app.models.enums import FriendshipStatus
from app.models.enums import ReservaStatus
from app.models.friends import Friends
from app.helpers.auth import ModelUser
from app.helpers.qr import qr_data_uri
from app.models.reserva import Reserva
from app.models.review import Review
from app.models.tag import Tag
from app.models.user import Role, User
from app.models.user_tags import UserTags
from app.helpers.validators import (
    ValidationError,
    validate_image_file,
    validate_int,
    validate_password,
    validate_password_confirmation,
    validate_tag_names,
    validate_text,
)


from app.routes.usuario import usuario_bp
ALLOWED_PROFILE_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

SETUP_EXEMPT_ENDPOINTS = {
    "auth.logout",
    "usuario.setup_gustos",
    "usuario.save_gustos",
    "usuario.save_setup",
    "usuario.sync_contacts",
    "usuario.complete_setup",
    "usuario.do_sync",
}

ARG_TZ = timezone(timedelta(hours=-3))
FRIEND_ELIGIBLE_ROLES = (Role.COMENSAL, Role.ADMIN_GLOBAL)


def _friend_display_name(user_record):
    return getattr(user_record, "name", None) or getattr(user_record, "username", "Usuario")


def _friend_initials(user_record):
    display_name = _friend_display_name(user_record).strip()
    parts = [part for part in display_name.split() if part]
    if len(parts) >= 2:
        return f"{parts[0][0]}{parts[1][0]}".upper()
    return display_name[:2].upper() or "US"


def _existing_friend_user_ids(user_id):
    relations = (
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
    connected_ids = set()
    for user_id_1, user_id_2 in relations:
        connected_ids.add(user_id_1)
        connected_ids.add(user_id_2)
    connected_ids.discard(user_id)
    return connected_ids


def _connectable_users(user_id):
    excluded_ids = _existing_friend_user_ids(user_id)
    query = (
        db.session.query(User)
        .filter(
            User.user_id != user_id,
            User.rol.in_(FRIEND_ELIGIBLE_ROLES),
            User.is_active.is_(True),
        )
        .order_by(func.lower(User.name), func.lower(User.username))
    )

    if excluded_ids:
        query = query.filter(User.user_id.notin_(excluded_ids))

    users = query.all()
    return [
        {
            "id": str(user.user_id),
            "name": _friend_display_name(user),
            "username": user.username,
            "initials": _friend_initials(user),
            "photo_url": getattr(user, "foto_perfil", None) or getattr(user, "avatar_url", None),
        }
        for user in users
    ]

@usuario_bp.before_app_request
def enforce_profile_setup():
    if not current_user.is_authenticated:
        return None

    if not getattr(current_user, "is_active", True):
        logout_user()
        flash("Tu cuenta está suspendida. Contactá al equipo de soporte.", "danger")
        return redirect(url_for("auth.login"))

    role_value = getattr(getattr(current_user, "rol", None), "value", None)
    if role_value not in {"comensal", "admin_global"}:
        return None

    endpoint = request.endpoint
    if not endpoint:
        return None

    if endpoint == "static" or endpoint.startswith("static"):
        return None

    if endpoint.startswith("auth."):
        return None

    if endpoint in SETUP_EXEMPT_ENDPOINTS:
        return None

    has_tags = (
        db.session.query(UserTags.user_id)
        .filter(UserTags.user_id == current_user.user_id)
        .first()
        is not None
    )

    if not has_tags:
        return redirect(url_for("usuario.setup_gustos"))

    return None


def _load_tag_options():
    all_tags = db.session.query(Tag).order_by(Tag.category, Tag.name).all()
    cuisine_tags = [tag for tag in all_tags if tag.category == TagCategory.COMIDA]
    restriction_tags = [tag for tag in all_tags if tag.category == TagCategory.DIETA]
    return all_tags, cuisine_tags, restriction_tags


def _selected_tag_names(user_record):
    cuisine_names = []
    restriction_names = []

    for user_tag in getattr(user_record, "user_tags", []):
        if not user_tag.tag:
            continue
        if user_tag.tag.category == TagCategory.COMIDA:
            cuisine_names.append(user_tag.tag.name)
        elif user_tag.tag.category == TagCategory.DIETA:
            restriction_names.append(user_tag.tag.name)

    return cuisine_names, restriction_names


def _build_sidebar_user_data(user_record):
    level_names = {
        1: "Invitado",
        2: "Foodie Curioso",
        3: "Catador Urbano",
        4: "Explorador Gourmet",
        5: "Leyenda Morfi",
    }
    raw_level = float(getattr(user_record, "nivel", 1) or 1)
    current_level_number = max(1, min(5, int(raw_level)))
    progress = int(round((raw_level - current_level_number) * 100))
    progress = max(0, min(100, progress))
    xp_missing = max(0, 500 - int((progress / 100) * 500))
    visits_count = db.session.query(Reserva).filter(Reserva.user_id == user_record.user_id).count()
    friends_count = (
        db.session.query(Friends)
        .filter(
            Friends.estado == FriendshipStatus.ACEPTADA,
            or_(Friends.user_id_1 == user_record.user_id, Friends.user_id_2 == user_record.user_id),
        )
        .count()
    )

    return {
        "name": getattr(user_record, "name", None) or getattr(user_record, "username", ""),
        "username": getattr(user_record, "username", ""),
        "photo_url": getattr(user_record, "foto_perfil", None) or getattr(user_record, "avatar_url", None),
        "stats": {"friends": friends_count, "visits": visits_count},
        "level": {
            "current": level_names[current_level_number],
            "next": level_names.get(min(current_level_number + 1, 5), ""),
            "progress": progress,
            "xp_missing": xp_missing,
        },
    }


def _friend_payloads(user_id):
    friendships = (
        db.session.query(Friends)
        .options(joinedload(Friends.user_1), joinedload(Friends.user_2))
        .filter(or_(Friends.user_id_1 == user_id, Friends.user_id_2 == user_id))
        .order_by(Friends.fecha.desc())
        .all()
    )

    accepted = []
    pending = []

    for friendship in friendships:
        friend_user = friendship.user_2 if friendship.user_id_1 == user_id else friendship.user_1
        if friend_user is None:
            continue

        payload = {
            "friendship_id": str(friendship.id_amistad),
            "id": str(friend_user.user_id),
            "name": _friend_display_name(friend_user),
            "username": friend_user.username,
            "initials": _friend_initials(friend_user),
            "photo_url": getattr(friend_user, "foto_perfil", None) or getattr(friend_user, "avatar_url", None),
            "can_respond": False,
            "status_text": "Amigo" if friendship.estado == FriendshipStatus.ACEPTADA else "Solicitud pendiente",
        }

        if friendship.estado == FriendshipStatus.ACEPTADA:
            accepted.append(payload)
        elif friendship.estado == FriendshipStatus.PENDIENTE:
            if friendship.user_id_2 == user_id:
                payload["status_text"] = "Solicitud recibida"
                payload["can_respond"] = True
            else:
                payload["status_text"] = "Solicitud enviada"
            pending.append(payload)

    return accepted, pending


def _accepted_friendship(user_id, friend_user_id):
    return (
        db.session.query(Friends)
        .filter(
            Friends.estado == FriendshipStatus.ACEPTADA,
            or_(
                and_(Friends.user_id_1 == user_id, Friends.user_id_2 == friend_user_id),
                and_(Friends.user_id_1 == friend_user_id, Friends.user_id_2 == user_id),
            ),
        )
        .first()
    )


def _save_profile_photo(uploaded_file):
    filename = secure_filename(uploaded_file.filename or "")
    _, extension = os.path.splitext(filename.lower())

    if not extension or extension not in ALLOWED_PROFILE_IMAGE_EXTENSIONS:
        raise ValueError("La foto debe ser JPG, PNG, WEBP o GIF.")

    upload_dir = os.path.join(current_app.root_path, "static", "uploads", "profile")
    os.makedirs(upload_dir, exist_ok=True)

    generated_name = f"{uuid.uuid4().hex}{extension}"
    destination = os.path.join(upload_dir, generated_name)
    uploaded_file.save(destination)

    return f"uploads/profile/{generated_name}"


def _validate_and_update_password(user_record, current_password, new_password, confirm_password):
    if not any([current_password, new_password, confirm_password]):
        return False

    if not all([current_password, new_password, confirm_password]):
        raise ValueError("Para cambiar la contraseña, debes completar los 3 campos.")

    validate_password(new_password)
    validate_password_confirmation(new_password, confirm_password)

    if not user_record.check_password(current_password):
        raise ValueError("La contraseña actual es incorrecta.")

    user_record.password = new_password
    return True


def _comparison_now_for_reservation(reservation_date):
    if reservation_date and reservation_date.tzinfo is not None:
        return datetime.now(timezone.utc).astimezone(reservation_date.tzinfo)
    return datetime.now()


def _refresh_restaurant_rating(restaurant_id):
    average_score = (
        db.session.query(func.avg(Review.puntaje))
        .join(Reserva, Review.id_reserva == Reserva.id_reserva)
        .filter(Reserva.id_restaurant == restaurant_id)
        .scalar()
    )
    restaurant = db.session.get(Restaurant, restaurant_id)
    if restaurant is not None:
        restaurant.puntaje = average_score or 0


@usuario_bp.route("/profile")
@usuario_bp.route("/perfil")
@login_required
def profile():
    user_record = ModelUser.get_by_id(db, current_user.get_id()) or current_user
    cuisine_names, restriction_names = _selected_tag_names(user_record)
    location_text = getattr(user_record, "address", "")
    level_names = {
        1: "Invitado",
        2: "Foodie Curioso",
        3: "Catador Urbano",
        4: "Explorador Gourmet",
        5: "Leyenda Morfi",
    }
    raw_level = float(getattr(user_record, "nivel", 1) or 1)
    current_level_number = max(1, min(5, int(raw_level)))
    current_level_name = level_names[current_level_number]
    next_level_name = level_names.get(min(current_level_number + 1, 5), current_level_name)
    progress = int(round((raw_level - current_level_number) * 100))
    progress = max(0, min(100, progress))
    xp_total = 500
    xp_current = int((progress / 100) * xp_total)
    xp_missing = max(0, xp_total - xp_current)
    display_name = getattr(user_record, "name", None) or getattr(user_record, "username", "Usuario")
    age = getattr(user_record, "age", None)
    member_since = f"{display_name} · {age} años" if age is not None else f"Rol: {getattr(user_record.rol, 'value', 'comensal').replace('_', ' ').title()}"
    visits_count = db.session.query(Reserva).filter(Reserva.user_id == user_record.user_id).count()
    friends_count = (
        db.session.query(Friends)
        .filter(
            Friends.estado == FriendshipStatus.ACEPTADA,
            or_(Friends.user_id_1 == user_record.user_id, Friends.user_id_2 == user_record.user_id),
        )
        .count()
    )
    recent_reservas = (
        db.session.query(Reserva)
        .filter(Reserva.user_id == user_record.user_id)
        .order_by(Reserva.fecha_hora.desc())
        .limit(3)
        .all()
    )
    recent_activity = [
        {
            "restaurant": reserva.restaurant.name if reserva.restaurant else "Reserva",
            "date": reserva.fecha_hora.strftime("%d/%m/%Y") if reserva.fecha_hora else "",
            "rating": reserva.review.puntaje if reserva.review else None,
            "comment": reserva.review.comentario if reserva.review and reserva.review.comentario else "Sin reseña cargada.",
        }
        for reserva in recent_reservas
    ]

    user_data = {
        "name": display_name,
        "username": getattr(user_record, "username", "Usuario"),
        "photo_url": getattr(user_record, "foto_perfil", None) or getattr(user_record, "avatar_url", None),
        "member_since": member_since,
        "email": getattr(user_record, "email", ""),
        "location": location_text,
        "role": getattr(getattr(user_record, "rol", None), "value", "comensal").replace("_", " ").title(),
        "age": age,
        "stats": {
            "visits": visits_count,
            "rewards": 0,
            "friends": friends_count,
        },
        "level": {
            "current": current_level_name,
            "progress": progress,
            "xp_current": xp_current,
            "xp_total": xp_total,
            "xp_missing": xp_missing,
            "next": next_level_name,
        },
        "levels": [
            {"number": number, "name": name, "active": number == current_level_number}
            for number, name in level_names.items()
        ],
        "quick_actions": [
            {"label": "Editar Perfil", "icon": "bi-pencil-square", "href": url_for("usuario.edit_profile")},
            {"label": "Historial", "icon": "bi-clock-history", "href": url_for("usuario.history")},
            {"label": "Wishlist", "icon": "bi-bookmark-heart", "href": url_for("usuario.wishlist")},
            {"label": "Admin", "icon": "bi-shield-lock", "href": url_for("restaurante.dashboard"), "admin_only": True},
        ],
        "favorite_cuisines": cuisine_names,
        "dietary_restrictions": restriction_names,
        "recent_activity": recent_activity,
        "is_admin": bool(getattr(user_record, "is_admin", False)),
        "is_global_admin": getattr(getattr(user_record, "rol", None), "value", None) == "admin_global",
        "system_panel_href": url_for("admin.restaurants"),
    }
    return render_template("usuario/profile.html", user=user_data)


@usuario_bp.route("/setup-gustos")
@login_required
def setup_gustos():
    all_tags, cuisine_tags, restriction_tags = _load_tag_options()

    return render_template(
        "usuario/profile_setup.html",
        all_tags=all_tags,
        cuisine_tags=cuisine_tags,
        restriction_tags=restriction_tags,
    )


@usuario_bp.route("/save-gustos", methods=["POST"])
@usuario_bp.route("/save-setup", methods=["POST"])
@login_required
def save_gustos():
    _, cuisine_tags, restriction_tags = _load_tag_options()
    cuisines = validate_tag_names(
        request.form.getlist("cuisines"),
        [tag.name for tag in cuisine_tags],
    )
    restrictions = validate_tag_names(
        request.form.getlist("restrictions"),
        [tag.name for tag in restriction_tags],
    )

    db.session.query(UserTags).filter(UserTags.user_id == current_user.user_id).delete(
        synchronize_session=False
    )

    selected_tags = (
        db.session.query(Tag)
        .filter(
            or_(
                and_(Tag.category == TagCategory.COMIDA, Tag.name.in_(cuisines)),
                and_(Tag.category == TagCategory.DIETA, Tag.name.in_(restrictions)),
            )
        )
        .all()
    )

    for tag in selected_tags:
        db.session.add(UserTags(user_id=current_user.user_id, id_tag=tag.id_tag))

    db.session.commit()
    return redirect(url_for("usuario.sync_contacts"))


@usuario_bp.route("/sync-contacts")
@login_required
def sync_contacts():
    return render_template(
        "usuario/sync_contacts.html",
        connectable_users=_connectable_users(current_user.user_id),
    )


@usuario_bp.route("/friends/<uuid:friend_id>/connect", methods=["POST"])
@login_required
def connect_friend(friend_id):
    wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    def _json_response(message, category, status_code=200):
        if wants_json:
            return jsonify({"ok": status_code < 400, "message": message, "category": category}), status_code
        flash(message, category)
        return None

    if friend_id == current_user.user_id:
        response = _json_response("No podés agregarte como amigo.", "warning", 400)
        return response or redirect(url_for("usuario.sync_contacts"))

    friend_user = (
        db.session.query(User)
        .filter(
            User.user_id == friend_id,
            User.rol.in_(FRIEND_ELIGIBLE_ROLES),
            User.is_active.is_(True),
        )
        .first()
    )
    if friend_user is None:
        response = _json_response("El usuario no está disponible para conectar.", "warning", 404)
        return response or redirect(url_for("usuario.sync_contacts"))

    existing_friendship = (
        db.session.query(Friends)
        .filter(
            or_(
                and_(Friends.user_id_1 == current_user.user_id, Friends.user_id_2 == friend_id),
                and_(Friends.user_id_1 == friend_id, Friends.user_id_2 == current_user.user_id),
            )
        )
        .first()
    )
    if existing_friendship is not None:
        if existing_friendship.estado == FriendshipStatus.RECHAZADA:
            try:
                existing_friendship.user_id_1 = current_user.user_id
                existing_friendship.user_id_2 = friend_id
                existing_friendship.estado = FriendshipStatus.PENDIENTE
                db.session.commit()
                response = _json_response("Solicitud enviada correctamente.", "success")
                if response:
                    return response
            except Exception:
                db.session.rollback()
                response = _json_response("No se pudo enviar la solicitud.", "danger", 500)
                return response or redirect(url_for("usuario.sync_contacts"))
            return redirect(url_for("usuario.sync_contacts"))

        if (
            existing_friendship.estado == FriendshipStatus.PENDIENTE
            and existing_friendship.user_id_2 == current_user.user_id
        ):
            response = _json_response("Ya tenés una solicitud pendiente de esta persona.", "warning", 400)
            return response or redirect(url_for("usuario.friends"))

        response = _json_response("Esa conexión ya existe.", "warning", 400)
        return response or redirect(url_for("usuario.sync_contacts"))

    try:
        db.session.add(
            Friends(
                user_id_1=current_user.user_id,
                user_id_2=friend_id,
                estado=FriendshipStatus.PENDIENTE,
            )
        )
        db.session.commit()

        # Notificación in-app + mail al destinatario
        try:
            from app.routes.usuario.notifications import crear_notificacion
            from app.helpers.mail import mail_solicitud_amistad
            solicitante_nombre = current_user.name or current_user.username
            crear_notificacion(
                user_id=friend_id,
                tipo="amistad",
                titulo=f"{solicitante_nombre} te envió una solicitud de amistad",
                url_destino="/perfil/amigos",
            )
            mail_solicitud_amistad(
                usuario_email=friend_user.email,
                usuario_nombre=friend_user.name or friend_user.username,
                solicitante_nombre=solicitante_nombre,
                user_id=friend_id,
            )
        except Exception:
            pass

        response = _json_response("Solicitud enviada correctamente.", "success")
        if response:
            return response
    except Exception:
        db.session.rollback()
        response = _json_response("No se pudo enviar la solicitud.", "danger", 500)
        return response or redirect(url_for("usuario.sync_contacts"))

    return redirect(url_for("usuario.sync_contacts"))


@usuario_bp.route("/friends/<uuid:friendship_id>/accept", methods=["POST"])
@login_required
def accept_friend_request(friendship_id):
    friendship = (
        db.session.query(Friends)
        .filter(
            Friends.id_amistad == friendship_id,
            Friends.user_id_2 == current_user.user_id,
            Friends.estado == FriendshipStatus.PENDIENTE,
        )
        .first_or_404()
    )

    try:
        friendship.estado = FriendshipStatus.ACEPTADA
        db.session.commit()
        flash("Solicitud aceptada.", "success")
    except Exception:
        db.session.rollback()
        flash("No se pudo aceptar la solicitud.", "danger")

    return redirect(url_for("usuario.friends"))


@usuario_bp.route("/friends/<uuid:friendship_id>/reject", methods=["POST"])
@login_required
def reject_friend_request(friendship_id):
    friendship = (
        db.session.query(Friends)
        .filter(
            Friends.id_amistad == friendship_id,
            Friends.user_id_2 == current_user.user_id,
            Friends.estado == FriendshipStatus.PENDIENTE,
        )
        .first_or_404()
    )

    try:
        friendship.estado = FriendshipStatus.RECHAZADA
        db.session.commit()
        flash("Solicitud rechazada.", "success")
    except Exception:
        db.session.rollback()
        flash("No se pudo rechazar la solicitud.", "danger")

    return redirect(url_for("usuario.friends"))


@usuario_bp.route("/complete-setup", methods=["POST"])
@usuario_bp.route("/do-sync", methods=["POST"])
@login_required
def complete_setup():
    db.session.commit()
    return redirect(url_for("usuario.home"))


@usuario_bp.route("/perfil/editar")
@login_required
def edit_profile():
    user_record = ModelUser.get_by_id(db, current_user.get_id()) or current_user
    _, cuisine_tags, restriction_tags = _load_tag_options()
    selected_cuisines, selected_restrictions = _selected_tag_names(user_record)

    return render_template(
        "usuario/edit_profile.html",
        user=user_record,
        location_text=getattr(user_record, "address", ""),
        cuisine_tags=cuisine_tags,
        restriction_tags=restriction_tags,
        selected_cuisines=selected_cuisines,
        selected_restrictions=selected_restrictions,
    )


@usuario_bp.route("/perfil/editar", methods=["POST"])
@login_required
def update_profile():
    user_record = ModelUser.get_by_id(db, current_user.get_id()) or current_user
    _, cuisine_tags, restriction_tags = _load_tag_options()
    updated_latitude = request.form.get("latitude")
    updated_longitude = request.form.get("longitude")
    uploaded_photo = request.files.get("profile_photo")
    current_password = request.form.get("current_password")
    new_password = request.form.get("new_password")
    confirm_password = request.form.get("confirm_password")

    try:
        updated_name = validate_text(request.form.get("name", ""), "El nombre completo", min_length=2, max_length=50)
        updated_location = validate_text(request.form.get("location", ""), "La ubicación", min_length=3, max_length=255)
        validate_image_file(uploaded_photo, field_label="La foto de perfil")
        cuisines = validate_tag_names(
            request.form.getlist("cuisines"),
            [tag.name for tag in cuisine_tags],
        )
        restrictions = validate_tag_names(
            request.form.getlist("restrictions"),
            [tag.name for tag in restriction_tags],
        )
        user_record.name = updated_name
    except ValidationError as ex:
        flash(str(ex), "warning")
        return redirect(url_for("usuario.edit_profile"))

    try:
        _validate_and_update_password(
            user_record,
            current_password,
            new_password,
            confirm_password,
        )
    except ValueError as ex:
        flash(str(ex), "warning")
        return redirect(url_for("usuario.edit_profile"))
        
    try:
        location_payload = resolve_location_payload(updated_location, updated_latitude, updated_longitude)
    except ValueError as ex:
        flash(str(ex), "warning")
        return redirect(url_for("usuario.edit_profile"))

    user_record.address = location_payload["address"]
    user_record.latitude = location_payload["latitude"]
    user_record.longitude = location_payload["longitude"]

    if uploaded_photo and uploaded_photo.filename:
        try:
            user_record.foto_perfil = _save_profile_photo(uploaded_photo)
        except ValueError as ex:
            flash(str(ex), "warning")
            return redirect(url_for("usuario.edit_profile"))

    db.session.query(UserTags).filter(UserTags.user_id == user_record.user_id).delete(
        synchronize_session=False
    )

    selected_tags = (
        db.session.query(Tag)
        .filter(
            or_(
                and_(Tag.category == TagCategory.COMIDA, Tag.name.in_(cuisines)),
                and_(Tag.category == TagCategory.DIETA, Tag.name.in_(restrictions)),
            )
        )
        .all()
    )

    for tag in selected_tags:
        db.session.add(UserTags(user_id=user_record.user_id, id_tag=tag.id_tag))

    db.session.commit()
    flash("Perfil actualizado correctamente.", "success")

    return redirect(url_for("usuario.profile"))


@usuario_bp.route("/perfil/historial")
@login_required
def history():
    user_record = ModelUser.get_by_id(db, current_user.get_id()) or current_user
    user_data = _build_sidebar_user_data(user_record)
    month_param = (request.args.get("month") or "").strip()
    now = datetime.now()

    if month_param:
        try:
            selected_month = datetime.strptime(month_param, "%Y-%m")
        except ValueError:
            selected_month = datetime(now.year, now.month, 1)
    else:
        selected_month = datetime(now.year, now.month, 1)

    month_value = selected_month.strftime("%Y-%m")
    month_start = datetime(selected_month.year, selected_month.month, 1)
    if selected_month.month == 12:
        next_month_start = datetime(selected_month.year + 1, 1, 1)
    else:
        next_month_start = datetime(selected_month.year, selected_month.month + 1, 1)

    solo_proximas = request.args.get("proximas") == "1"

    query = (
        db.session.query(Reserva)
        .options(joinedload(Reserva.restaurant), joinedload(Reserva.review))
        .filter(Reserva.user_id == user_record.user_id)
    )

    if solo_proximas:
        query = query.filter(Reserva.fecha_hora >= datetime.now(ARG_TZ)).order_by(Reserva.fecha_hora.asc())
    else:
        query = query.filter(
            Reserva.fecha_hora >= month_start,
            Reserva.fecha_hora < next_month_start,
        ).order_by(Reserva.fecha_hora.desc())

    reservations = query.all()

    month_names = {
        1: "ene",
        2: "feb",
        3: "mar",
        4: "abr",
        5: "may",
        6: "jun",
        7: "jul",
        8: "ago",
        9: "sep",
        10: "oct",
        11: "nov",
        12: "dic",
    }

    reservations_payload = []
    visited_payload = []
    for reserva in reservations:
        restaurant = reserva.restaurant
        reservation_date = reserva.fecha_hora
        comparison_now = _comparison_now_for_reservation(reservation_date)
        status_label = None
        status_variant = None
        action_label = None
        can_cancel = (
            reserva.estado_reserva == ReservaStatus.CONFIRMADA
            and reservation_date is not None
            and reservation_date > comparison_now
        )

        reserva_qr = None
        sena_pendiente = False
        if can_cancel:
            pago_aprobado = True
            if restaurant and restaurant.requiere_sena:
                pago_aprobado = (
                    db.session.query(Pago)
                    .filter_by(id_reserva=reserva.id_reserva, estado="approved")
                    .first() is not None
                )
            if pago_aprobado:
                if not reserva.token_validacion:
                    reserva.token_validacion = uuid.uuid4().hex
                    db.session.commit()
                reserva_qr = qr_data_uri(reserva.token_validacion)
            else:
                sena_pendiente = True

        estado_value = getattr(getattr(reserva, "estado_reserva", None), "value", None)
        if estado_value == "cancelada":
            status_label = "Cancelada"
            status_variant = "cancelled"
        elif estado_value == "completada":
            status_label = "Asistió"
            status_variant = "attended"
            action_label = "Dejar reseña"
        elif reservation_date and reservation_date <= comparison_now:
            status_label = "No asistió"
            status_variant = "missed"

        reservation_payload = {
            "restaurant_name": restaurant.name if restaurant else "Reserva",
            "restaurant_id": str(restaurant.id_restaurant) if restaurant else None,
            "reservation_id": str(reserva.id_reserva),
            "image_path": (
                getattr(restaurant, "cover_url", None)
                or getattr(restaurant, "logo_url", None)
                or None
            ),
            "date_label": (
                f"{reservation_date.day} {month_names[reservation_date.month]} {reservation_date.year}"
                if reservation_date
                else ""
            ),
            "time_label": (
                reservation_date.astimezone(ARG_TZ).strftime("%H:%M")
                if reservation_date and reservation_date.tzinfo
                else reservation_date.strftime("%H:%M") if reservation_date else ""
            ),
            "diners_label": f"{reserva.cant_personas} comensales",
            "status_label": status_label,
            "status_variant": status_variant,
            "action_label": action_label,
            "can_cancel": can_cancel,
            "review_rating": reserva.review.puntaje if reserva.review else None,
            "review_comment": reserva.review.comentario if reserva.review else "",
            "has_review": reserva.review is not None,
            "qr_data_uri": reserva_qr,
            "sena_pendiente": sena_pendiente,
        }
        if reserva.estado_reserva == ReservaStatus.COMPLETADA:
            visited_payload.append(
                {
                    **reservation_payload,
                    "status_label": "Asistió",
                    "status_variant": "attended",
                    "action_label": "Ver reseña" if reserva.review else "Dejar reseña",
                    "can_cancel": False,
                }
            )
        else:
            reservations_payload.append(reservation_payload)

    return render_template(
        "usuario/history.html",
        user=user_data,
        reservations=reservations_payload,
        visited_reservations=visited_payload,
        selected_month=month_value,
        solo_proximas=solo_proximas,
    )


@usuario_bp.route("/perfil/amigos")
@login_required
def friends():
    user_record = ModelUser.get_by_id(db, current_user.get_id()) or current_user
    user_data = _build_sidebar_user_data(user_record)
    accepted_friends, pending_friends = _friend_payloads(user_record.user_id)
    connectable_users = _connectable_users(user_record.user_id)

    return render_template(
        "usuario/friends.html",
        user=user_data,
        accepted_friends=accepted_friends,
        pending_friends=pending_friends,
        connectable_users=connectable_users,
    )


@usuario_bp.route("/perfil/amigos/<uuid:friend_user_id>")
@login_required
def friend_profile(friend_user_id):
    if _accepted_friendship(current_user.user_id, friend_user_id) is None:
        flash("Solo podés ver el perfil de tus amigos.", "warning")
        return redirect(url_for("usuario.friends"))

    friend_user = (
        db.session.query(User)
        .filter(
            User.user_id == friend_user_id,
            User.rol.in_(FRIEND_ELIGIBLE_ROLES),
            User.is_active.is_(True),
        )
        .first_or_404()
    )

    visits_count = (
        db.session.query(Reserva)
        .filter(
            Reserva.user_id == friend_user.user_id,
            Reserva.estado_reserva == ReservaStatus.COMPLETADA,
        )
        .count()
    )
    friends_count = (
        db.session.query(Friends)
        .filter(
            Friends.estado == FriendshipStatus.ACEPTADA,
            or_(Friends.user_id_1 == friend_user.user_id, Friends.user_id_2 == friend_user.user_id),
        )
        .count()
    )
    visited_restaurants = (
        db.session.query(Reserva)
        .options(joinedload(Reserva.restaurant))
        .filter(
            Reserva.user_id == friend_user.user_id,
            Reserva.estado_reserva == ReservaStatus.COMPLETADA,
        )
        .order_by(Reserva.fecha_hora.desc())
        .all()
    )

    visited_history = []
    for reserva in visited_restaurants:
        restaurant = reserva.restaurant
        visited_history.append(
            {
                "restaurant_name": restaurant.name if restaurant else "Restaurante",
                "restaurant_id": str(restaurant.id_restaurant) if restaurant else None,
                "image_path": (
                    getattr(restaurant, "cover_url", None)
                    or getattr(restaurant, "logo_url", None)
                    or None
                ),
                "date_label": reserva.fecha_hora.strftime("%d/%m/%Y") if reserva.fecha_hora else "",
            }
        )

    wishlist_items = (
        db.session.query(UserFavorites)
        .options(joinedload(UserFavorites.restaurant))
        .filter(UserFavorites.user_id == friend_user.user_id)
        .order_by(UserFavorites.fecha_agregado.desc())
        .all()
    )
    wishlist_payload = []
    for favorite in wishlist_items:
        restaurant = favorite.restaurant
        wishlist_payload.append(
            {
                "restaurant_name": restaurant.name if restaurant else "Restaurante",
                "restaurant_id": str(restaurant.id_restaurant) if restaurant else None,
                "image_path": (
                    getattr(restaurant, "cover_url", None)
                    or getattr(restaurant, "logo_url", None)
                    or None
                ),
            }
        )

    friend_data = {
        "id": str(friend_user.user_id),
        "name": getattr(friend_user, "name", None) or getattr(friend_user, "username", "Usuario"),
        "username": getattr(friend_user, "username", "usuario"),
        "photo_url": getattr(friend_user, "foto_perfil", None) or getattr(friend_user, "avatar_url", None),
        "stats": {
            "friends": friends_count,
            "visits": visits_count,
        },
        "visited_history": visited_history,
        "wishlist": wishlist_payload,
    }

    viewer_data = _build_sidebar_user_data(ModelUser.get_by_id(db, current_user.get_id()) or current_user)

    return render_template(
        "usuario/friend_profile.html",
        user=viewer_data,
        friend=friend_data,
    )


@usuario_bp.route("/perfil/amigos/<uuid:friend_user_id>/eliminar", methods=["POST"])
@login_required
def delete_friend(friend_user_id):
    friendship = _accepted_friendship(current_user.user_id, friend_user_id)
    if friendship is None:
        flash("Esa amistad no existe o ya fue eliminada.", "warning")
        return redirect(url_for("usuario.friends"))

    try:
        db.session.delete(friendship)
        db.session.commit()
        flash("Amigo eliminado correctamente.", "success")
    except Exception:
        db.session.rollback()
        flash("No se pudo eliminar el amigo.", "danger")
        return redirect(url_for("usuario.friend_profile", friend_user_id=friend_user_id))

    return redirect(url_for("usuario.friends"))


@usuario_bp.route("/perfil/reservas/<uuid:id_reserva>/cancelar", methods=["POST"])
@login_required
def cancel_user_reservation(id_reserva):
    reservation = (
        db.session.query(Reserva)
        .filter(
            Reserva.id_reserva == id_reserva,
            Reserva.user_id == current_user.user_id,
        )
        .first_or_404()
    )

    comparison_now = _comparison_now_for_reservation(reservation.fecha_hora)
    redirect_month = (request.form.get("month") or "").strip()
    redirect_kwargs = {"month": redirect_month} if redirect_month else {}

    if reservation.estado_reserva != ReservaStatus.CONFIRMADA:
        flash("Solo podés cancelar reservas confirmadas.", "warning")
        return redirect(url_for("usuario.history", **redirect_kwargs))

    if reservation.fecha_hora and reservation.fecha_hora <= comparison_now:
        flash("No podés cancelar una reserva cuya fecha ya pasó.", "warning")
        return redirect(url_for("usuario.history", **redirect_kwargs))

    try:
        reservation.estado_reserva = ReservaStatus.CANCELADA
        db.session.commit()
        flash("Reserva cancelada correctamente.", "success")
    except Exception:
        db.session.rollback()
        flash("No se pudo cancelar la reserva.", "danger")

    return redirect(url_for("usuario.history", **redirect_kwargs))


@usuario_bp.route("/perfil/reservas/<uuid:id_reserva>/review", methods=["POST"])
@login_required
def save_user_review(id_reserva):
    reservation = (
        db.session.query(Reserva)
        .options(joinedload(Reserva.review), joinedload(Reserva.restaurant))
        .filter(
            Reserva.id_reserva == id_reserva,
            Reserva.user_id == current_user.user_id,
        )
        .first_or_404()
    )

    redirect_month = (request.form.get("month") or "").strip()
    redirect_kwargs = {"month": redirect_month} if redirect_month else {}

    if reservation.estado_reserva != ReservaStatus.COMPLETADA:
        flash("Solo podés dejar reseñas de reservas a las que asististe.", "warning")
        return redirect(url_for("usuario.history", **redirect_kwargs))

    try:
        rating = validate_int(
            request.form.get("rating", ""),
            "El puntaje",
            min_value=1,
            max_value=5,
        )
        comment = validate_text(
            request.form.get("comment", ""),
            "La reseña",
            required=False,
            max_length=500,
        )
    except ValidationError as ex:
        flash(str(ex), "warning")
        return redirect(url_for("usuario.history", **redirect_kwargs))

    if reservation.review is not None:
        flash("Esta reseña ya fue publicada y no se puede modificar.", "warning")
        return redirect(url_for("usuario.history", **redirect_kwargs))

    try:
        review = reservation.review
        if review is None:
            review = Review(
                id_reserva=reservation.id_reserva,
                puntaje=rating,
                comentario=comment or None,
            )
            db.session.add(review)
        else:
            review.puntaje = rating
            review.comentario = comment or None

        _refresh_restaurant_rating(reservation.id_restaurant)
        db.session.commit()
        flash("Reseña guardada correctamente.", "success")
    except Exception:
        db.session.rollback()
        flash("No se pudo guardar la reseña.", "danger")

    return redirect(url_for("usuario.history", **redirect_kwargs))


@usuario_bp.route("/perfil/reservas/<uuid:id_reserva>/review/delete", methods=["POST"])
@login_required
def delete_user_review(id_reserva):
    reservation = (
        db.session.query(Reserva)
        .options(joinedload(Reserva.review))
        .filter(
            Reserva.id_reserva == id_reserva,
            Reserva.user_id == current_user.user_id,
        )
        .first_or_404()
    )

    redirect_month = (request.form.get("month") or "").strip()
    redirect_kwargs = {"month": redirect_month} if redirect_month else {}

    if reservation.review is None:
        flash("Esa reserva no tiene reseña cargada.", "warning")
        return redirect(url_for("usuario.history", **redirect_kwargs))

    try:
        db.session.delete(reservation.review)
        _refresh_restaurant_rating(reservation.id_restaurant)
        db.session.commit()
        flash("Reseña eliminada correctamente.", "success")
    except Exception:
        db.session.rollback()
        flash("No se pudo eliminar la reseña.", "danger")

    return redirect(url_for("usuario.history", **redirect_kwargs))

@usuario_bp.route("/perfil/seguridad")
@login_required
def security():
    """Página Cuenta y seguridad — reutiliza los mismos datos que profile()."""
    user_record = ModelUser.get_by_id(db, current_user.get_id()) or current_user
    cuisine_names, restriction_names = _selected_tag_names(user_record)
    user_data = _build_sidebar_user_data(user_record)
    user_data["favorite_cuisines"] = cuisine_names
    user_data["dietary_restrictions"] = restriction_names
    return render_template(
        "usuario/cuenta_seguridad.html",
        user=user_data,
        open_password_modal=request.args.get("password_modal") == "1",
    )


@usuario_bp.route("/perfil/seguridad/cambiar-contrasena", methods=["POST"])
@login_required
def update_security_password():
    user_record = ModelUser.get_by_id(db, current_user.get_id()) or current_user
    current_password = request.form.get("current_password") or ""
    new_password = request.form.get("new_password") or ""
    confirm_password = request.form.get("confirm_password") or ""

    try:
        changed = _validate_and_update_password(
            user_record,
            current_password,
            new_password,
            confirm_password,
        )
        if not changed:
            flash("Completá los campos para cambiar la contraseña.", "warning")
            return redirect(url_for("usuario.security", password_modal="1"))

        db.session.commit()
        flash("Contraseña actualizada correctamente.", "success")
    except ValueError as ex:
        flash(str(ex), "warning")
        return redirect(url_for("usuario.security", password_modal="1"))
    except Exception:
        db.session.rollback()
        flash("No se pudo actualizar la contraseña.", "danger")
        return redirect(url_for("usuario.security", password_modal="1"))

    return redirect(url_for("usuario.security"))
 
 
@usuario_bp.route("/perfil/eliminar-cuenta", methods=["POST"])
@login_required
def delete_account():
    """Elimina permanentemente la cuenta del usuario autenticado."""
    user_id = current_user.user_id
 
    try:
        # 1. Reviews se eliminan en cascada junto con Reservas (cascade="all, delete-orphan")
        # 2. Eliminamos Reservas
        db.session.query(Reserva).filter(Reserva.user_id == user_id).delete(
            synchronize_session=False
        )
 
        # 3. Eliminamos relaciones de amistad
        db.session.query(Friends).filter(
            or_(Friends.user_id_1 == user_id, Friends.user_id_2 == user_id)
        ).delete(synchronize_session=False)
 
        # 4. Eliminamos tags del usuario
        db.session.query(UserTags).filter(UserTags.user_id == user_id).delete(
            synchronize_session=False
        )
 
        # 5. Cerramos sesión ANTES de borrar el usuario
        logout_user()
 
        # 6. Eliminamos el usuario
        user_record = db.session.query(User).filter(User.user_id == user_id).first()
        if user_record:
            db.session.delete(user_record)
 
        db.session.commit()
        flash("Tu cuenta fue eliminada correctamente.", "info")
 
    except Exception:
        db.session.rollback()
        flash("No se pudo eliminar la cuenta. Intentá de nuevo.", "danger")
        return redirect(url_for("usuario.security"))
 
    return redirect(url_for("auth.index"))


# ── Wishlist ──────────────────────────────────────────────────────

DEFAULT_LIST_ID = "default"
DEFAULT_LIST_NAME = "Guardados"


@usuario_bp.route("/perfil/wishlist")
@login_required
def wishlist():
    user_record = ModelUser.get_by_id(db, current_user.get_id()) or current_user

    # Listas nombradas del usuario (la default "Guardados" es virtual, no se persiste).
    named_lists = (
        db.session.query(Wishlist)
        .filter_by(user_id=current_user.user_id)
        .order_by(Wishlist.created_at.asc())
        .all()
    )

    favorites = (
        db.session.query(UserFavorites)
        .filter_by(user_id=current_user.user_id)
        .join(UserFavorites.restaurant)
        .order_by(UserFavorites.fecha_agregado.desc())
        .all()
    )

    items = (
        db.session.query(WishlistItem)
        .join(Wishlist, Wishlist.id == WishlistItem.wishlist_id)
        .join(WishlistItem.restaurant)
        .filter(Wishlist.user_id == current_user.user_id)
        .order_by(WishlistItem.fecha_agregado.desc())
        .all()
    )

    # "Visitado" = el usuario tiene una reserva COMPLETADA en ese restaurante.
    visited_ids = {
        str(row[0])
        for row in db.session.query(Reserva.id_restaurant)
        .filter(
            Reserva.user_id == current_user.user_id,
            Reserva.estado_reserva == ReservaStatus.COMPLETADA,
        )
        .distinct()
        .all()
    }

    def _card(r):
        return {
            "id":        str(r.id_restaurant),
            "name":      r.name,
            "rating":    round(float(r.puntaje or 0), 1),
            "cover_url": r.cover_url,
            "visited":   str(r.id_restaurant) in visited_ids,
        }

    buckets = {DEFAULT_LIST_ID: [_card(fav.restaurant) for fav in favorites]}
    for wl in named_lists:
        buckets[str(wl.id)] = []
    for it in items:
        buckets.setdefault(str(it.wishlist_id), []).append(_card(it.restaurant))

    lists = [{
        "id":       DEFAULT_LIST_ID,
        "name":     DEFAULT_LIST_NAME,
        "removable": False,
        "cards":    buckets[DEFAULT_LIST_ID],
    }]
    for wl in named_lists:
        lists.append({
            "id":        str(wl.id),
            "name":      wl.nombre,
            "removable": True,
            "cards":     buckets[str(wl.id)],
        })

    total = len(favorites)
    user_data = _build_sidebar_user_data(user_record)
    return render_template(
        "usuario/wishlist.html",
        user=user_data,
        lists=lists,
        total=total,
    )


@usuario_bp.route("/perfil/wishlist/toggle/<restaurant_id>", methods=["POST"])
@login_required
def toggle_wishlist(restaurant_id):
    from uuid import UUID as _UUID
    try:
        rid = _UUID(restaurant_id)
    except ValueError:
        return jsonify({"error": "ID inválido"}), 400

    restaurant = db.session.query(Restaurant).filter_by(id_restaurant=rid).first()
    if not restaurant:
        return jsonify({"error": "Restaurante no encontrado"}), 404

    existing = db.session.query(UserFavorites).filter_by(
        user_id=current_user.user_id,
        id_restaurante=rid,
    ).first()

    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({"in_wishlist": False})
    else:
        # Al guardar, el restaurante entra a la lista por defecto "Guardados".
        db.session.add(UserFavorites(user_id=current_user.user_id, id_restaurante=rid))
        db.session.commit()
        return jsonify({"in_wishlist": True})


@usuario_bp.route("/perfil/wishlist/listas/crear", methods=["POST"])
@login_required
def crear_wishlist_lista():
    nombre = (request.form.get("nombre") or "").strip()
    if not nombre:
        return jsonify({"error": "El nombre no puede estar vacío"}), 400
    if len(nombre) > 60:
        nombre = nombre[:60]

    # Evita listas duplicadas con el mismo nombre.
    ya_existe = (
        db.session.query(Wishlist)
        .filter(Wishlist.user_id == current_user.user_id, func.lower(Wishlist.nombre) == nombre.lower())
        .first()
    )
    if ya_existe:
        return jsonify({"error": "Ya tenés una lista con ese nombre"}), 409

    nueva = Wishlist(user_id=current_user.user_id, nombre=nombre)
    db.session.add(nueva)
    db.session.commit()
    return jsonify({"id": str(nueva.id), "name": nueva.nombre})


@usuario_bp.route("/perfil/wishlist/listas/<uuid:list_id>/renombrar", methods=["POST"])
@login_required
def renombrar_wishlist_lista(list_id):
    nombre = (request.form.get("nombre") or "").strip()
    if not nombre:
        return jsonify({"error": "El nombre no puede estar vacío"}), 400
    if len(nombre) > 60:
        nombre = nombre[:60]

    lista = (
        db.session.query(Wishlist)
        .filter_by(id=list_id, user_id=current_user.user_id)
        .first()
    )
    if not lista:
        return jsonify({"error": "Lista no encontrada"}), 404

    lista.nombre = nombre
    db.session.commit()
    return jsonify({"id": str(lista.id), "name": lista.nombre})


@usuario_bp.route("/perfil/wishlist/listas/<uuid:list_id>/eliminar", methods=["POST"])
@login_required
def eliminar_wishlist_lista(list_id):
    lista = (
        db.session.query(Wishlist)
        .filter_by(id=list_id, user_id=current_user.user_id)
        .first()
    )
    if not lista:
        return jsonify({"error": "Lista no encontrada"}), 404

    db.session.delete(lista)
    db.session.commit()
    return jsonify({"ok": True})


@usuario_bp.route("/perfil/wishlist/listas/<uuid:list_id>/toggle/<restaurant_id>", methods=["POST"])
@login_required
def toggle_wishlist_list(list_id, restaurant_id):
    from uuid import UUID as _UUID
    try:
        rid = _UUID(restaurant_id)
    except ValueError:
        return jsonify({"error": "ID inválido"}), 400

    lista = db.session.query(Wishlist).filter_by(
        id=list_id, user_id=current_user.user_id
    ).first()
    if not lista:
        return jsonify({"error": "Lista no encontrada"}), 404

    if not db.session.query(Restaurant).filter_by(id_restaurant=rid).first():
        return jsonify({"error": "Restaurante no encontrado"}), 404

    item = db.session.query(WishlistItem).filter_by(
        wishlist_id=list_id, id_restaurante=rid
    ).first()

    if item:
        db.session.delete(item)
        db.session.commit()
        return jsonify({"in_list": False})

    db.session.add(WishlistItem(wishlist_id=list_id, id_restaurante=rid))
    db.session.commit()
    return jsonify({"in_list": True})


@usuario_bp.route("/perfil/wishlist/listas/estado/<restaurant_id>")
@login_required
def estado_wishlist_listas(restaurant_id):
    from uuid import UUID as _UUID
    try:
        rid = _UUID(restaurant_id)
    except ValueError:
        return jsonify({"error": "ID inválido"}), 400

    saved = db.session.query(UserFavorites).filter_by(
        user_id=current_user.user_id, id_restaurante=rid
    ).first() is not None

    named_lists = (
        db.session.query(Wishlist)
        .filter_by(user_id=current_user.user_id)
        .order_by(Wishlist.created_at.asc())
        .all()
    )

    en_listas = {
        str(row[0])
        for row in db.session.query(WishlistItem.wishlist_id)
        .join(Wishlist, Wishlist.id == WishlistItem.wishlist_id)
        .filter(Wishlist.user_id == current_user.user_id, WishlistItem.id_restaurante == rid)
        .all()
    }

    return jsonify({
        "saved": saved,
        "lists": [
            {"id": str(wl.id), "name": wl.nombre, "in_list": str(wl.id) in en_listas}
            for wl in named_lists
        ],
    })