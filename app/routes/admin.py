from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.database import db
from app.models.user import Role, User


admin_bp = Blueprint("admin", __name__)


def _admin_required():
    return bool(getattr(current_user, "is_admin", False))


@admin_bp.route("/admin/dashboard")
@login_required
def dashboard():
    if not _admin_required():
        flash("No tenés permisos para acceder al panel de administración.", "danger")
        return redirect(url_for("profile.profile"))

    users = db.session.query(User).order_by(User.is_admin.desc(), User.username.asc()).all()

    total_users = len(users)
    total_admins = sum(1 for user in users if user.is_admin)
    role_labels = {
        Role.COMENSAL.value: "Comensal",
        Role.SOCIO_RESTAURANTE.value: "Socio restaurante",
        Role.ADMIN_GLOBAL.value: "Admin global",
    }
    profiles = []
    for user in users:
        role_value = getattr(getattr(user, "rol", None), "value", Role.COMENSAL.value)
        profiles.append(
            {
                "id": str(user.user_id),
                "route_id": user.user_id,
                "username": user.username,
                "name": user.name or "Sin nombre cargado",
                "email": user.email,
                "role": role_labels.get(role_value, role_value.replace("_", " ").title()),
                "level": float(user.nivel or 1),
                "age": user.age,
                "is_admin": bool(user.is_admin),
                "can_delete": str(user.user_id) != current_user.get_id(),
            }
        )

    dashboard_data = {
        "stats": {
            "pending_reviews": 12,
            "partners_in_review": 5,
            "active_restaurants": 247,
            "total_users": total_users,
            "total_admins": total_admins,
            "total_comensales": sum(1 for user in users if getattr(user.rol, "value", None) == Role.COMENSAL.value),
        },
        "profiles": profiles,
    }
    return render_template("admin_dashboard.html", dashboard=dashboard_data)


@admin_bp.route("/admin/users/<uuid:user_id>/delete", methods=["POST"])
@login_required
def delete_user(user_id):
    if not _admin_required():
        flash("No tenés permisos para realizar esta acción.", "danger")
        return redirect(url_for("profile.profile"))

    user = db.session.get(User, user_id)
    if user is None:
        flash("El perfil que intentaste eliminar no existe.", "warning")
        return redirect(url_for("admin.dashboard"))

    if str(user.user_id) == current_user.get_id():
        flash("No podés eliminar tu propio perfil desde el panel de administración.", "warning")
        return redirect(url_for("admin.dashboard"))

    username = user.username
    db.session.delete(user)
    db.session.commit()
    flash(f"El perfil de {username} fue eliminado correctamente.", "success")
    return redirect(url_for("admin.dashboard"))
