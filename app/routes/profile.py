from flask import Blueprint, render_template, url_for
from flask_login import current_user, login_required

from app.database import db
from app.models.modelUser import ModelUser


profile_bp = Blueprint("profile", __name__)


@profile_bp.route("/profile")
@profile_bp.route("/perfil")
@login_required
def profile():
    user_record = ModelUser.get_by_id(db, current_user.get_id()) or current_user
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

    user_data = {
        "name": display_name,
        "username": getattr(user_record, "username", "Usuario"),
        "member_since": member_since,
        "email": getattr(user_record, "email", ""),
        "role": getattr(getattr(user_record, "rol", None), "value", "comensal").replace("_", " ").title(),
        "age": age,
        "stats": {
            "visits": 0,
            "rewards": 0,
            "friends": 0,
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
            {"label": "Historial", "icon": "bi-clock-history", "href": "#"},
            {"label": "Wishlist", "icon": "bi-bookmark-heart", "href": "#"},
            {"label": "Admin", "icon": "bi-shield-lock", "href": "#", "admin_only": True},
        ],
        "rewards_list": [
            {"title": "20% OFF en Parrilla", "location": "La Parrilla Criolla", "value": "20%"},
            {"title": "Postre Gratis", "location": "Bistro del Puerto", "value": "1x"},
            {"title": "2x1 en Cafes", "location": "Cafe Central", "value": "2x1"},
            {"title": "Entrada VIP", "location": "Mercado Gourmet", "value": "VIP"},
        ],
        "is_admin": bool(getattr(user_record, "is_admin", False)),
    }
    return render_template("profile.html", user=user_data)


@profile_bp.route("/perfil/editar")
@login_required
def edit_profile():
    return render_template("edit_profile.html", user=current_user)
