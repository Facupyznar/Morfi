import os
import uuid

from sqlalchemy import and_, func, or_

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, logout_user
from werkzeug.utils import secure_filename

from app.models.user_favorites import UserFavorites
from app.database import db
from app.location import resolve_location_payload
from app.models.enums import TagCategory
from app.models.enums import FriendshipStatus
from app.models.friends import Friends
from app.models.modelUser import ModelUser
from app.models.reserva import Reserva
from app.models.tag import Tag
from app.models.user import User
from app.models.user_tags import UserTags


profile_bp = Blueprint("profile", __name__)
ALLOWED_PROFILE_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

SETUP_EXEMPT_ENDPOINTS = {
    "auth.logout",
    "profile.setup_gustos",
    "profile.save_gustos",
    "profile.save_setup",
    "profile.sync_contacts",
    "profile.complete_setup",
    "profile.do_sync",
}


@profile_bp.before_app_request
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
        return redirect(url_for("profile.setup_gustos"))

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


@profile_bp.route("/profile")
@profile_bp.route("/perfil")
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
            {"label": "Editar Perfil", "icon": "bi-pencil-square", "href": url_for("profile.edit_profile")},
            {"label": "Historial", "icon": "bi-clock-history", "href": url_for("profile.history")},
            {"label": "Wishlist", "icon": "bi-bookmark-heart", "href": "#"},
            {"label": "Admin", "icon": "bi-shield-lock", "href": url_for("admin.dashboard"), "admin_only": True},
        ],
        "favorite_cuisines": cuisine_names,
        "dietary_restrictions": restriction_names,
        "recent_activity": recent_activity,
        "is_admin": bool(getattr(user_record, "is_admin", False)),
        "is_global_admin": getattr(getattr(user_record, "rol", None), "value", None) == "admin_global",
        "system_panel_href": url_for("system.restaurants"),
    }
    return render_template("profile.html", user=user_data)


@profile_bp.route("/setup-gustos")
@login_required
def setup_gustos():
    all_tags, cuisine_tags, restriction_tags = _load_tag_options()

    return render_template(
        "profile_setup.html",
        all_tags=all_tags,
        cuisine_tags=cuisine_tags,
        restriction_tags=restriction_tags,
    )


@profile_bp.route("/save-gustos", methods=["POST"])
@profile_bp.route("/save-setup", methods=["POST"])
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
    return redirect(url_for("profile.sync_contacts"))


@profile_bp.route("/sync-contacts")
@login_required
def sync_contacts():
    return render_template("sync_contacts.html")


@profile_bp.route("/complete-setup", methods=["POST"])
@profile_bp.route("/do-sync", methods=["POST"])
@login_required
def complete_setup():
    db.session.commit()
    return redirect(url_for("home.home"))


@profile_bp.route("/perfil/editar")
@login_required
def edit_profile():
    user_record = ModelUser.get_by_id(db, current_user.get_id()) or current_user
    _, cuisine_tags, restriction_tags = _load_tag_options()
    selected_cuisines, selected_restrictions = _selected_tag_names(user_record)

    return render_template(
        "edit_profile.html",
        user=user_record,
        location_text=getattr(user_record, "address", ""),
        cuisine_tags=cuisine_tags,
        restriction_tags=restriction_tags,
        selected_cuisines=selected_cuisines,
        selected_restrictions=selected_restrictions,
    )


@profile_bp.route("/perfil/editar", methods=["POST"])
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

    if updated_name:
        user_record.name = updated_name
    else:
        flash("El nombre no puede estar vacío.", "warning")
        return redirect(url_for("profile.edit_profile"))

    try:
        location_payload = resolve_location_payload(updated_location, updated_latitude, updated_longitude)
    except ValueError as ex:
        flash(str(ex), "warning")
        return redirect(url_for("profile.edit_profile"))

    user_record.address = location_payload["address"]
    user_record.latitude = location_payload["latitude"]
    user_record.longitude = location_payload["longitude"]

    if uploaded_photo and uploaded_photo.filename:
        try:
            user_record.foto_perfil = _save_profile_photo(uploaded_photo)
        except ValueError as ex:
            flash(str(ex), "warning")
            return redirect(url_for("profile.edit_profile"))

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

    return redirect(url_for("profile.profile"))


@profile_bp.route("/perfil/historial")
@login_required
def history():
    return render_template("history.html")

@profile_bp.route("/perfil/seguridad")
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
    return render_template("cuenta_seguridad.html", user=user_data)
 
 
@profile_bp.route("/perfil/eliminar-cuenta", methods=["POST"])
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
        return redirect(url_for("profile.security"))
 
    return redirect(url_for("auth.index"))