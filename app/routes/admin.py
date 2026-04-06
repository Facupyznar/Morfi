from decimal import Decimal, InvalidOperation

from sqlalchemy import and_, or_

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.database import db
from app.location import resolve_location_payload
from app.models.enums import TagCategory
from app.models.menu import Menu
from app.models.menu_tags import MenuTags
from app.models.restaurant import Restaurant
from app.models.restaurant_tags import RestaurantTags
from app.models.tag import Tag
from app.models.user import Role, User


admin_bp = Blueprint("admin", __name__)
MENU_DEFAULT_CATEGORIES = ["Entradas", "Carnes", "Guarniciones", "Postres"]


def _admin_required():
    role_value = getattr(getattr(current_user, "rol", None), "value", None)
    return role_value == Role.SOCIO_ADMIN.value


def _get_owned_restaurant():
    return (
        db.session.query(Restaurant)
        .filter(Restaurant.id_owner == current_user.user_id)
        .first()
    )


def _build_menu_view_data(restaurant):
    menus = (
        db.session.query(Menu)
        .filter(Menu.id_restaurant == restaurant.id_restaurant)
        .order_by(Menu.nombre.asc())
        .all()
    )

    menu_items = []
    category_names = []
    for item in menus:
        category_tag = next(
            (
                relation.tag.name
                for relation in item.menu_tags
                if relation.tag and relation.tag.category == TagCategory.COMIDA
            ),
            None,
        )
        fallback_tag = next((relation.tag.name for relation in item.menu_tags if relation.tag), None)
        category_name = category_tag or fallback_tag or "Sin categoría"
        category_names.append(category_name)
        menu_items.append(
            {
                "id": str(item.id_plato),
                "name": item.nombre,
                "category": category_name,
                "price": float(item.precio or 0),
                "available": bool(item.disponibilidad),
                "photo_label": (item.nombre or "?")[:1].upper(),
            }
        )

    categories = ["Todas"]
    categories.extend(sorted(set(category_names)) or MENU_DEFAULT_CATEGORIES)
    return {"menu_items": menu_items, "categories": categories}


@admin_bp.route("/admin/dashboard")
@login_required
def dashboard():
    if not _admin_required():
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
    return render_template(
        "admin_dashboard.html",
        dashboard=dashboard_data,
        active_admin_section="Inicio",
    )


@admin_bp.route("/admin/menu", methods=["GET", "POST"])
@login_required
def menu():
    if not _admin_required():
        return redirect(url_for("home.home"))

    restaurant = _get_owned_restaurant()
    if restaurant is None:
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        description = (request.form.get("description") or "").strip()
        category_name = (request.form.get("category") or "").strip()
        raw_price = (request.form.get("price") or "").strip()

        if not name:
            return redirect(url_for("admin.menu", open_drawer=1))

        if not category_name:
            return redirect(url_for("admin.menu", open_drawer=1))

        try:
            price = Decimal(raw_price)
        except (InvalidOperation, TypeError):
            return redirect(url_for("admin.menu", open_drawer=1))

        if price <= 0:
            return redirect(url_for("admin.menu", open_drawer=1))

        item = Menu(
            id_restaurant=restaurant.id_restaurant,
            nombre=name,
            precio=price,
            disponibilidad=True,
            tags=description or None,
        )
        db.session.add(item)
        db.session.flush()

        category_tag = db.session.query(Tag).filter(Tag.name == category_name).first()
        if category_tag is None:
            category_tag = Tag(name=category_name, category=TagCategory.COMIDA)
            db.session.add(category_tag)
            db.session.flush()

        db.session.add(MenuTags(id_plato=item.id_plato, id_tag=category_tag.id_tag))
        db.session.commit()
        return redirect(url_for("admin.menu"))

    view_data = _build_menu_view_data(restaurant)

    return render_template(
        "admin_menu.html",
        menu_items=view_data["menu_items"],
        categories=view_data["categories"],
        active_admin_section="Menú",
        open_drawer=request.args.get("open_drawer") == "1",
    )



@admin_bp.route("/admin/profile/edit")
@login_required
def edit_restaurant_profile():
    if not _admin_required():
        return redirect(url_for("home.home"))

    restaurant = _get_owned_restaurant()
    if restaurant is None:
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
        return redirect(url_for("home.home"))

    restaurant = _get_owned_restaurant()
    if restaurant is None:
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
        return redirect(url_for("admin.edit_restaurant_profile"))

    try:
        location_payload = resolve_location_payload(address, latitude, longitude)
    except ValueError as ex:
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
    return redirect(url_for("admin.edit_restaurant_profile"))


@admin_bp.route("/admin/users/<uuid:user_id>/delete", methods=["POST"])
@login_required
def delete_user(user_id):
    if not _admin_required():
        return redirect(url_for("profile.profile"))

    user = db.session.get(User, user_id)
    if user is None:
        return redirect(url_for("admin.dashboard"))

    if str(user.user_id) == current_user.get_id():
        return redirect(url_for("admin.dashboard"))

    username = user.username
    db.session.delete(user)
    db.session.commit()
    return redirect(url_for("admin.dashboard"))
