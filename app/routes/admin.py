from sqlalchemy import and_, or_

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.database import db
from app.location import resolve_location_payload
from app.models.enums import TagCategory
from app.models.restaurant import Restaurant
from app.models.restaurant_tags import RestaurantTags
from app.models.tag import Tag
from app.models.user import Role, User


admin_bp = Blueprint("admin", __name__)


def _admin_required():
    role_value = getattr(getattr(current_user, "rol", None), "value", None)
    return role_value == Role.SOCIO_ADMIN.value


def _get_owned_restaurant():
    return (
        db.session.query(Restaurant)
        .filter(Restaurant.id_owner == current_user.user_id)
        .first()
    )


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
        Role.SOCIO_ADMIN.value: "Socio admin",
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


@admin_bp.route("/admin/profile/edit")
@login_required
def edit_restaurant_profile():
    if not _admin_required():
        flash("No tenés permisos para acceder a esta pantalla.", "danger")
        return redirect(url_for("home.home"))

    restaurant = _get_owned_restaurant()
    if restaurant is None:
        flash("No encontramos un restaurante asociado a tu cuenta.", "warning")
        return redirect(url_for("admin.dashboard"))

    all_tags = db.session.query(Tag).order_by(Tag.category, Tag.name).all()
    cuisine_tags = [tag for tag in all_tags if tag.category == TagCategory.COMIDA]
    ambience_tags = [tag for tag in all_tags if tag.category == TagCategory.AMBIENTE]
    occasion_tags = [tag for tag in all_tags if tag.category == TagCategory.OCASION]
    selected_tag_names = [item.tag.name for item in restaurant.restaurant_tags if item.tag]

    return render_template(
        "admin_edit_profile.html",
        restaurant=restaurant,
        cuisine_tags=cuisine_tags,
        ambience_tags=ambience_tags,
        occasion_tags=occasion_tags,
        selected_tag_names=selected_tag_names,
        active_admin_section="Perfil",
    )


@admin_bp.route("/admin/profile/edit", methods=["POST"])
@login_required
def update_restaurant_profile():
    if not _admin_required():
        flash("No tenés permisos para realizar esta acción.", "danger")
        return redirect(url_for("home.home"))

    restaurant = _get_owned_restaurant()
    if restaurant is None:
        flash("No encontramos un restaurante asociado a tu cuenta.", "warning")
        return redirect(url_for("admin.dashboard"))

    name = (request.form.get("name") or "").strip()
    address = (request.form.get("address") or "").strip()
    latitude = request.form.get("latitude")
    longitude = request.form.get("longitude")
    cuisines = [value.strip() for value in request.form.getlist("cuisines") if value.strip()]
    ambience = [value.strip() for value in request.form.getlist("ambience") if value.strip()]
    occasions = [value.strip() for value in request.form.getlist("occasions") if value.strip()]
    selected_tag_names = cuisines + ambience + occasions

    if not name:
        flash("El nombre del restaurante es obligatorio.", "warning")
        return redirect(url_for("admin.edit_restaurant_profile"))

    try:
        location_payload = resolve_location_payload(address, latitude, longitude)
    except ValueError as ex:
        flash(str(ex), "warning")
        return redirect(url_for("admin.edit_restaurant_profile"))

    restaurant.name = name
    restaurant.address = location_payload["address"]
    restaurant.latitude = location_payload["latitude"]
    restaurant.longitude = location_payload["longitude"]

    current_user.name = name
    current_user.address = location_payload["address"]
    current_user.latitude = location_payload["latitude"]
    current_user.longitude = location_payload["longitude"]

    db.session.query(RestaurantTags).filter(
        RestaurantTags.id_restaurant == restaurant.id_restaurant
    ).delete(synchronize_session=False)

    selected_tags = (
        db.session.query(Tag)
        .filter(
            or_(
                and_(Tag.category == TagCategory.COMIDA, Tag.name.in_(cuisines)),
                and_(Tag.category == TagCategory.AMBIENTE, Tag.name.in_(ambience)),
                and_(Tag.category == TagCategory.OCASION, Tag.name.in_(occasions)),
            )
        )
        .all()
    )

    for tag in selected_tags:
        db.session.add(RestaurantTags(id_restaurant=restaurant.id_restaurant, id_tag=tag.id_tag))

    db.session.commit()
    flash("Perfil del restaurante actualizado correctamente.", "success")
    return redirect(url_for("admin.edit_restaurant_profile"))


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
