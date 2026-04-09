import uuid
from collections import defaultdict
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
        selected_tags = sorted(
            [relation.tag for relation in item.menu_tags if relation.tag],
            key=lambda tag: (getattr(getattr(tag, "category", None), "value", ""), tag.name or ""),
        )
        selected_tag_names = [tag.name for tag in selected_tags]
        category_label = ", ".join(selected_tag_names) or item.categoria or "Sin tags"
        category_names.extend(selected_tag_names)
        menu_items.append(
            {
                "id": str(item.id_plato),
                "name": item.nombre,
                "description": item.descripcion or "",
                "category": category_label,
                "selected_tag_ids": [str(tag.id_tag) for tag in selected_tags],
                "selected_tag_names": selected_tag_names,
                "price": float(item.precio or 0),
                "available": bool(item.disponibilidad),
                "photo_label": (item.nombre or "?")[:1].upper(),
            }
        )

    categories = ["Todas"]
    categories.extend(sorted(set(category_names)) or MENU_DEFAULT_CATEGORIES)
    return {"menu_items": menu_items, "categories": categories}


def _get_owned_menu_item(restaurant, item_id):
    return (
        db.session.query(Menu)
        .filter(
            Menu.id_plato == item_id,
            Menu.id_restaurant == restaurant.id_restaurant,
        )
        .first()
    )


def _menu_tag_group_title(category):
    labels = {
        TagCategory.COMIDA: "Tipo de plato",
        TagCategory.DIETA: "Dietas y restricciones",
        TagCategory.OTRO: "Otros tags",
    }
    return labels.get(category, getattr(category, "value", "Tags").replace("_", " ").title())


def _build_available_menu_tags():
    allowed_categories = [TagCategory.COMIDA, TagCategory.DIETA, TagCategory.OTRO]
    tag_records = (
        db.session.query(Tag)
        .filter(Tag.category.in_(allowed_categories))
        .order_by(Tag.category.asc(), Tag.name.asc())
        .all()
    )

    grouped_tags = defaultdict(list)
    for tag in tag_records:
        grouped_tags[tag.category].append(
            {
                "id": str(tag.id_tag),
                "name": tag.name,
            }
        )

    ordered_groups = []
    for category in allowed_categories:
        tags = grouped_tags.get(category, [])
        if tags:
            ordered_groups.append(
                {
                    "slug": getattr(category, "value", str(category)),
                    "title": _menu_tag_group_title(category),
                    "tags": tags,
                }
            )
    return ordered_groups


def _resolve_selected_menu_tags(raw_tag_ids):
    normalized_ids = []
    for raw_tag_id in raw_tag_ids:
        try:
            normalized_ids.append(uuid.UUID(str(raw_tag_id)))
        except (TypeError, ValueError, AttributeError):
            continue

    if not normalized_ids:
        return []

    selected_tags = (
        db.session.query(Tag)
        .filter(Tag.id_tag.in_(normalized_ids))
        .order_by(Tag.category.asc(), Tag.name.asc())
        .all()
    )
    return selected_tags


def _upsert_menu_item(item, *, restaurant, name, description, selected_tags, price, available):
    item.id_restaurant = restaurant.id_restaurant
    item.nombre = name
    item.precio = price
    item.disponibilidad = available
    item.descripcion = description or None
    item.categoria = ", ".join(tag.name for tag in selected_tags) or None
    db.session.add(item)
    db.session.flush()

    db.session.query(MenuTags).filter(
        MenuTags.id_plato == item.id_plato
    ).delete(synchronize_session=False)
    for tag in selected_tags:
        db.session.add(MenuTags(id_plato=item.id_plato, id_tag=tag.id_tag))


@admin_bp.route("/admin/dashboard")
@login_required
def dashboard():
    if not _admin_required():
        return redirect(url_for("profile.profile"))

    from datetime import date
    DIAS_ES   = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    MESES_ES  = ["","enero","febrero","marzo","abril","mayo","junio",
                 "julio","agosto","septiembre","octubre","noviembre","diciembre"]

    hoy = date.today()
    today_label = f"{DIAS_ES[hoy.weekday()]} {hoy.day} de {MESES_ES[hoy.month]}"

    # ── Restaurante del usuario actual ───────────────────────
    restaurant_record = _get_owned_restaurant()
    restaurant = {"name": restaurant_record.name} if restaurant_record else {"name": "Mi restaurante"}

    # ── Usuarios ─────────────────────────────────────────────
    users = db.session.query(User).order_by(User.is_admin.desc(), User.username.asc()).all()
    total_users   = len(users)
    total_admins  = sum(1 for u in users if u.is_admin)
    role_labels = {
        Role.COMENSAL.value:    "Comensal",
        Role.SOCIO_ADMIN.value: "Socio admin",
        Role.ADMIN_GLOBAL.value:"Admin global",
    }
    profiles = []
    for user in users:
        role_value = getattr(getattr(user, "rol", None), "value", Role.COMENSAL.value)
        profiles.append({
            "id":        str(user.user_id),
            "route_id":  user.user_id,
            "username":  user.username,
            "name":      user.name or "Sin nombre",
            "email":     user.email,
            "role":      role_labels.get(role_value, role_value),
            "level":     float(user.nivel or 1),
            "is_admin":  bool(user.is_admin),
            "can_delete":str(user.user_id) != current_user.get_id(),
        })

    # ── Reservas de hoy ──────────────────────────────────────
    reservas_hoy = []
    if restaurant_record:
        from app.models.reserva import Reserva
        from sqlalchemy import cast, Date

    reservas_db = (
        db.session.query(Reserva)
        .filter(
            Reserva.id_restaurant == restaurant_record.id_restaurant,
            cast(Reserva.fecha_hora, Date) == hoy
        )
        .order_by(Reserva.fecha_hora)
        .limit(10)
        .all()
    )
    for r in reservas_db:
        u = db.session.query(User).filter_by(user_id=r.user_id).first()
        nombre = u.name if u else "Cliente"
        reservas_hoy.append({
            "initials": nombre[:2].upper(),
            "nombre":   nombre,
            "hora":     r.fecha_hora.strftime('%H:%M'),
            "personas": r.cant_personas,
            "estado":   "Confirmada" if r.estado_reserva.value == "CONFIRMADA" else "Pendiente",
        })

    # ── Ocupación semanal (mock por ahora) ───────────────────
    ocupacion_semanal = [
        {"dia": d, "pct": p, "hoy": i == hoy.weekday()}
        for i, (d, p) in enumerate(zip(
            DIAS_ES, [65, 58, 72, 85, 92, 78, 40]
        ))
    ]

    dashboard_data = {
        "stats": {
            "reservas_hoy":        len(reservas_hoy),
            "reservas_delta":      len(reservas_hoy),
            "pending_reviews":     12,
            "partners_in_review":  5,
            "active_restaurants":  247,
            "total_users":         total_users,
            "total_admins":        total_admins,
            "total_comensales":    sum(1 for u in users if getattr(u.rol, "value", None) == Role.COMENSAL.value),
        },
        "profiles": profiles,
    }

    return render_template(
        "admin_dashboard.html",
        dashboard=dashboard_data,
        restaurant=restaurant,
        today_label=today_label,
        reservas_hoy=reservas_hoy,
        ocupacion_semanal=ocupacion_semanal,
        alert=None,
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
        selected_tags = _resolve_selected_menu_tags(request.form.getlist("tag_ids"))
        raw_price = (request.form.get("price") or "").strip()

        if not name:
            return redirect(url_for("admin.menu", open_drawer=1))

        if not selected_tags:
            return redirect(url_for("admin.menu", open_drawer=1))

        try:
            price = Decimal(raw_price)
        except (InvalidOperation, TypeError):
            return redirect(url_for("admin.menu", open_drawer=1))

        if price <= 0:
            return redirect(url_for("admin.menu", open_drawer=1))

        item = Menu()
        _upsert_menu_item(
            item,
            restaurant=restaurant,
            name=name,
            description=description,
            selected_tags=selected_tags,
            price=price,
            available=True,
        )
        db.session.commit()
        flash("Plato agregado correctamente.", "success")
        return redirect(url_for("admin.menu"))

    view_data = _build_menu_view_data(restaurant)

    return render_template(
        "admin_menu.html",
        menu_items=view_data["menu_items"],
        categories=view_data["categories"],
        menu_tag_groups=_build_available_menu_tags(),
        active_admin_section="Menú",
        open_drawer=request.args.get("open_drawer") == "1",
    )


@admin_bp.route("/admin/menu/<uuid:item_id>/edit", methods=["POST"])
@login_required
def edit_menu_item(item_id):
    if not _admin_required():
        return redirect(url_for("home.home"))

    restaurant = _get_owned_restaurant()
    if restaurant is None:
        return redirect(url_for("admin.dashboard"))

    item = _get_owned_menu_item(restaurant, item_id)
    if item is None:
        flash("No se encontró el plato a editar.", "danger")
        return redirect(url_for("admin.menu"))

    name = (request.form.get("name") or "").strip()
    description = (request.form.get("description") or "").strip()
    selected_tags = _resolve_selected_menu_tags(request.form.getlist("tag_ids"))
    raw_price = (request.form.get("price") or "").strip()

    if not name or not selected_tags:
        flash("Completá nombre y al menos un tag para editar el plato.", "warning")
        return redirect(url_for("admin.menu", open_drawer=1))

    try:
        price = Decimal(raw_price)
    except (InvalidOperation, TypeError):
        flash("Ingresá un precio válido.", "warning")
        return redirect(url_for("admin.menu", open_drawer=1))

    if price <= 0:
        flash("El precio debe ser mayor a cero.", "warning")
        return redirect(url_for("admin.menu", open_drawer=1))

    _upsert_menu_item(
        item,
        restaurant=restaurant,
        name=name,
        description=description,
        selected_tags=selected_tags,
        price=price,
        available=bool(item.disponibilidad),
    )
    db.session.commit()
    flash("Plato actualizado correctamente.", "success")
    return redirect(url_for("admin.menu"))


@admin_bp.route("/admin/menu/<uuid:item_id>/delete", methods=["POST"])
@login_required
def delete_menu_item(item_id):
    if not _admin_required():
        return redirect(url_for("home.home"))

    restaurant = _get_owned_restaurant()
    if restaurant is None:
        return redirect(url_for("admin.dashboard"))

    item = _get_owned_menu_item(restaurant, item_id)
    if item is None:
        flash("No se encontró el plato a eliminar.", "danger")
        return redirect(url_for("admin.menu"))

    db.session.delete(item)
    db.session.commit()
    flash("Plato eliminado correctamente.", "success")
    return redirect(url_for("admin.menu"))


@admin_bp.route("/admin/menu/<uuid:item_id>/availability", methods=["POST"])
@login_required
def update_menu_item_availability(item_id):
    if not _admin_required():
        return redirect(url_for("home.home"))

    restaurant = _get_owned_restaurant()
    if restaurant is None:
        return redirect(url_for("admin.dashboard"))

    item = _get_owned_menu_item(restaurant, item_id)
    if item is None:
        flash("No se encontró el plato para actualizar disponibilidad.", "danger")
        return redirect(url_for("admin.menu"))

    item.disponibilidad = request.form.get("available") == "1"
    db.session.commit()
    flash("Disponibilidad actualizada correctamente.", "success")
    return redirect(url_for("admin.menu"))



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
