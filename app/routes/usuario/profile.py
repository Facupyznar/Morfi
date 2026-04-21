from datetime import datetime, timezone, timedelta
import os
import uuid

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import joinedload

from flask import current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required, logout_user
from werkzeug.utils import secure_filename

from app.models.user_favorites import UserFavorites
from app.models.restaurant import Restaurant
from app.database import db
from app.location import resolve_location_payload
from app.models.enums import TagCategory
from app.models.enums import FriendshipStatus
from app.models.enums import ReservaStatus
from app.models.friends import Friends
from app.helpers.auth import ModelUser
from app.models.reserva import Reserva
from app.models.tag import Tag
from app.models.user import User
from app.models.user_tags import UserTags


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

    if new_password != confirm_password:
        raise ValueError("Las contraseñas no coinciden.")

    if not user_record.check_password(current_password):
        raise ValueError("La contraseña actual es incorrecta.")

    if len(new_password) <= 4:
        raise ValueError("La contraseña debe tener más de 4 caracteres.")

    user_record.password = new_password
    return True


def _comparison_now_for_reservation(reservation_date):
    if reservation_date and reservation_date.tzinfo is not None:
        return datetime.now(timezone.utc).astimezone(reservation_date.tzinfo)
    return datetime.now()


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
        "photo_url": getattr(user_record, "foto_perfil", None),
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
    cuisines = [value.strip() for value in request.form.getlist("cuisines") if value.strip()]
    restrictions = [value.strip() for value in request.form.getlist("restrictions") if value.strip()]

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
    return render_template("usuario/sync_contacts.html")


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
    updated_name = (request.form.get("name") or "").strip()
    updated_location = (request.form.get("location") or "").strip()
    updated_latitude = request.form.get("latitude")
    updated_longitude = request.form.get("longitude")
    uploaded_photo = request.files.get("profile_photo")
    cuisines = [value.strip() for value in request.form.getlist("cuisines") if value.strip()]
    restrictions = [value.strip() for value in request.form.getlist("restrictions") if value.strip()]
    current_password = request.form.get("current_password")
    new_password = request.form.get("new_password")
    confirm_password = request.form.get("confirm_password")

    if updated_name:
        user_record.name = updated_name
    else:
        flash("El nombre no puede estar vacío.", "warning")
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

    reservations = (
        db.session.query(Reserva)
        .options(joinedload(Reserva.restaurant), joinedload(Reserva.review))
        .filter(
            Reserva.user_id == user_record.user_id,
            Reserva.fecha_hora >= month_start,
            Reserva.fecha_hora < next_month_start,
        )
        .order_by(Reserva.fecha_hora.desc())
        .all()
    )

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

        if getattr(getattr(reserva, "estado_reserva", None), "value", None) == "cancelada":
            status_label = "Cancelada"
            status_variant = "cancelled"
        elif reservation_date and reservation_date <= comparison_now:
            if getattr(getattr(reserva, "estado_reserva", None), "value", None) == "completada":
                status_label = "Asistió"
                status_variant = "attended"
                action_label = "Dejar reseña"
            else:
                status_label = "No asistió"
                status_variant = "missed"

        reservations_payload.append(
            {
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
                "time_label":(
                    reservation_date.astimezone(ARG_TZ).strftime("%H:%M")
                    if reservation_date and reservation_date.tzinfo
                    else reservation_date.strftime("%H:%M") if reservation_date else ""

                ),
                "diners_label": f"{reserva.cant_personas} comensales",
                "status_label": status_label,
                "status_variant": status_variant,
                "action_label": action_label,
                "can_cancel": can_cancel,
            }
        )

    return render_template(
        "usuario/history.html",
        reservations=reservations_payload,
        selected_month=month_value,
    )


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

@usuario_bp.route("/perfil/seguridad")
@login_required
def security():
    """Página Cuenta y seguridad — reutiliza los mismos datos que profile()."""
    user_record = ModelUser.get_by_id(db, current_user.get_id()) or current_user
    cuisine_names, restriction_names = _selected_tag_names(user_record)
 
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
 
    visits_count = db.session.query(Reserva).filter(
        Reserva.user_id == user_record.user_id
    ).count()
    friends_count = (
        db.session.query(Friends)
        .filter(
            Friends.estado == FriendshipStatus.ACEPTADA,
            or_(
                Friends.user_id_1 == user_record.user_id,
                Friends.user_id_2 == user_record.user_id,
            ),
        )
        .count()
    )
 
    user_data = {
        "name": getattr(user_record, "name", None) or getattr(user_record, "username", ""),
        "username": getattr(user_record, "username", ""),
        "stats": {"friends": friends_count, "visits": visits_count},
        "level": {
            "current": level_names[current_level_number],
            "next": level_names.get(min(current_level_number + 1, 5), ""),
            "progress": progress,
            "xp_missing": xp_missing,
        },
        "favorite_cuisines": cuisine_names,
        "dietary_restrictions": restriction_names,
    }
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

@usuario_bp.route("/perfil/wishlist")
@login_required
def wishlist():
    user_record = ModelUser.get_by_id(db, current_user.get_id()) or current_user
    favorites = (
        db.session.query(UserFavorites)
        .filter_by(user_id=current_user.user_id)
        .join(UserFavorites.restaurant)
        .order_by(UserFavorites.fecha_agregado.desc())
        .all()
    )
    wishlist_items = []
    for fav in favorites:
        r = fav.restaurant
        wishlist_items.append({
            "id":       str(r.id_restaurant),
            "name":     r.name,
            "rating":   round(float(r.puntaje or 0), 1),
            "cover_url": r.cover_url,
        })

    level_names = {1: "Invitado", 2: "Foodie Curioso", 3: "Catador Urbano", 4: "Explorador Gourmet", 5: "Leyenda Morfi"}
    raw_level = float(getattr(user_record, "nivel", 1) or 1)
    current_level_number = max(1, min(5, int(raw_level)))
    progress = int(round((raw_level - current_level_number) * 100))
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

    user_data = {
        "name":     getattr(user_record, "name", None) or getattr(user_record, "username", ""),
        "username": getattr(user_record, "username", ""),
        "photo_url": getattr(user_record, "foto_perfil", None),
        "stats": {"friends": friends_count, "visits": visits_count},
        "level": {
            "current":   level_names[current_level_number],
            "next":      level_names.get(min(current_level_number + 1, 5), ""),
            "progress":  progress,
            "xp_missing": xp_missing,
        },
    }
    return render_template("usuario/wishlist.html", user=user_data, wishlist=wishlist_items)


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
        db.session.add(UserFavorites(user_id=current_user.user_id, id_restaurante=rid))
        db.session.commit()
        return jsonify({"in_wishlist": True})
