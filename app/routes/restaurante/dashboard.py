import json
import os
import uuid
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from sqlalchemy import and_, extract, or_
from werkzeug.utils import secure_filename

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.database import db
from app.location import resolve_location_payload
from app.models.enums import TagCategory
from app.models.menu import Menu
from app.models.menu_tags import MenuTags
from app.models.reserva import Reserva
from app.models.restaurant import Restaurant
from app.models.restaurant_tags import RestaurantTags
from app.models.tag import Tag
from app.models.user import Role, User

# ── File upload helpers ──────────────────────────────────────────────────────
_ALLOWED_IMG = {"png", "jpg", "jpeg", "webp"}
_MAX_GALLERY  = 10


def _allowed_img(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in _ALLOWED_IMG


def _save_img(file, subfolder: str, prefix: str) -> str | None:
    """Guarda un FileStorage en static/uploads/restaurants/<subfolder>/ y
    devuelve el path relativo a static/ (para usar con url_for('static', ...))."""
    if not file or not file.filename:
        return None
    if not _allowed_img(file.filename):
        return None
    ext  = secure_filename(file.filename).rsplit(".", 1)[-1].lower()
    name = f"{prefix}_{uuid.uuid4().hex[:10]}.{ext}"
    folder = os.path.join(current_app.static_folder, "uploads", "restaurants", subfolder)
    os.makedirs(folder, exist_ok=True)
    file.save(os.path.join(folder, name))
    return f"uploads/restaurants/{subfolder}/{name}"


from app.routes.restaurante import restaurante_bp
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
    category_set = set()
    for item in menus:
        selected_tags = sorted(
            [relation.tag for relation in item.menu_tags if relation.tag],
            key=lambda tag: (getattr(getattr(tag, "category", None), "value", ""), tag.name or ""),
        )
        selected_tag_names = [tag.name for tag in selected_tags]
        # Priorizar item.categoria (campo directo del formulario); si no hay, derivar de tags
        category_label = item.categoria or ", ".join(selected_tag_names) or "Sin categoría"
        if category_label:
            category_set.add(category_label)
        foto_url = getattr(item, "foto_url", None)
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
                "foto_url": foto_url,
            }
        )

    categories = ["Todas"]
    categories.extend(sorted(category_set) if category_set else MENU_DEFAULT_CATEGORIES)
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


def _upsert_menu_item(item, *, restaurant, name, description, selected_tags, price, available, categoria=None, foto_url=None):
    item.id_restaurant = restaurant.id_restaurant
    item.nombre = name
    item.precio = price
    item.disponibilidad = available
    item.descripcion = description or None
    # Si se pasa categoria explícita (nuevo campo del formulario), usarla; si no, derivar de tags
    item.categoria = categoria or ", ".join(tag.name for tag in selected_tags) or None
    if foto_url:
        item.foto_url = foto_url
    db.session.add(item)
    db.session.flush()

    db.session.query(MenuTags).filter(
        MenuTags.id_plato == item.id_plato
    ).delete(synchronize_session=False)
    for tag in selected_tags:
        db.session.add(MenuTags(id_plato=item.id_plato, id_tag=tag.id_tag))


@restaurante_bp.route("/restaurante/dashboard")
@login_required
def dashboard():
    if not _admin_required():
        return redirect(url_for("usuario.profile"))

    from datetime import date
    DIAS_ES   = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    MESES_ES  = ["","enero","febrero","marzo","abril","mayo","junio",
                 "julio","agosto","septiembre","octubre","noviembre","diciembre"]

    hoy = date.today()
    today_label = f"{DIAS_ES[hoy.weekday()]} {hoy.day} de {MESES_ES[hoy.month]}"

    # ── Restaurante del usuario actual ───────────────────────
    restaurant_record = _get_owned_restaurant()
    restaurant = {
        "name":    restaurant_record.name,
        "puntaje": float(restaurant_record.puntaje or 0),
    } if restaurant_record else {"name": "Mi restaurante", "puntaje": 0}

    # ── Clientes recientes de este restaurante ───────────────
    from app.models.reserva import Reserva as _Reserva
    from datetime import date as _date
    import calendar as _calendar

    mes_inicio = _date(hoy.year, hoy.month, 1)
    mes_fin    = _date(hoy.year, hoy.month, _calendar.monthrange(hoy.year, hoy.month)[1])

    reservas_mes = 0
    clientes_mes = 0
    profiles = []

    if restaurant_record:
        reservas_mes = (
            db.session.query(_Reserva)
            .filter(
                _Reserva.id_restaurant == restaurant_record.id_restaurant,
                _Reserva.fecha_hora >= mes_inicio,
                _Reserva.fecha_hora <= mes_fin,
            )
            .count()
        )

        # Clientes únicos (comensales) con reservas en este restaurante
        user_ids_con_reserva = (
            db.session.query(_Reserva.user_id)
            .filter(_Reserva.id_restaurant == restaurant_record.id_restaurant)
            .distinct()
            .subquery()
        )
        clientes = (
            db.session.query(User)
            .filter(
                User.user_id.in_(user_ids_con_reserva),
                User.rol == Role.COMENSAL,
            )
            .order_by(User.username.asc())
            .limit(8)
            .all()
        )
        clientes_mes = (
            db.session.query(User)
            .filter(User.user_id.in_(user_ids_con_reserva))
            .count()
        )
        for user in clientes:
            profiles.append({
                "username": user.username,
                "name":     user.name or "Sin nombre",
                "email":    user.email,
                "level":    float(user.nivel or 1),
                "is_admin": False,
                "role":     "Comensal",
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
            "reservas_hoy":     len(reservas_hoy),
            "reservas_delta":   len(reservas_hoy),
            "reservas_mes":     reservas_mes,
            "clientes_totales": clientes_mes,
        },
        "profiles": profiles,
    }

    return render_template(
        "restaurante/dashboard.html",
        dashboard=dashboard_data,
        restaurant=restaurant,
        today_label=today_label,
        reservas_hoy=reservas_hoy,
        ocupacion_semanal=ocupacion_semanal,
        alert=None,
        active_admin_section="Inicio",
    )

@restaurante_bp.route("/restaurante/menu", methods=["GET", "POST"])
@login_required
def menu():
    if not _admin_required():
        return redirect(url_for("usuario.home"))

    restaurant = _get_owned_restaurant()
    if restaurant is None:
        return redirect(url_for("restaurante.dashboard"))

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        description = (request.form.get("description") or "").strip()
        categoria = (request.form.get("categoria") or "").strip() or None
        selected_tags = _resolve_selected_menu_tags(request.form.getlist("tag_ids"))
        raw_price = (request.form.get("price") or "").strip()
        available = request.form.get("available", "1") == "1"

        if not name:
            flash("El nombre del plato es requerido.", "warning")
            return redirect(url_for("restaurante.menu", open_drawer=1))

        try:
            price = Decimal(raw_price)
        except (InvalidOperation, TypeError):
            flash("Ingresá un precio válido.", "warning")
            return redirect(url_for("restaurante.menu", open_drawer=1))

        if price <= 0:
            flash("El precio debe ser mayor a cero.", "warning")
            return redirect(url_for("restaurante.menu", open_drawer=1))

        # Guardar foto del plato si se subió una
        foto_url = None
        foto_file = request.files.get("foto")
        if foto_file and foto_file.filename:
            foto_url = _save_img(foto_file, "menu", str(restaurant.id_restaurant))

        item = Menu()
        _upsert_menu_item(
            item,
            restaurant=restaurant,
            name=name,
            description=description,
            selected_tags=selected_tags,
            price=price,
            available=available,
            categoria=categoria,
            foto_url=foto_url,
        )
        db.session.commit()
        flash("Plato agregado correctamente.", "success")
        return redirect(url_for("restaurante.menu"))

    view_data = _build_menu_view_data(restaurant)

    return render_template(
        "restaurante/menu.html",
        menu_items=view_data["menu_items"],
        categories=view_data["categories"],
        menu_tag_groups=_build_available_menu_tags(),
        active_admin_section="Menú",
        open_drawer=request.args.get("open_drawer") == "1",
    )


@restaurante_bp.route("/restaurante/menu/<uuid:item_id>/edit", methods=["POST"])
@login_required
def edit_menu_item(item_id):
    if not _admin_required():
        return redirect(url_for("usuario.home"))

    restaurant = _get_owned_restaurant()
    if restaurant is None:
        return redirect(url_for("restaurante.dashboard"))

    item = _get_owned_menu_item(restaurant, item_id)
    if item is None:
        flash("No se encontró el plato a editar.", "danger")
        return redirect(url_for("restaurante.menu"))

    name = (request.form.get("name") or "").strip()
    description = (request.form.get("description") or "").strip()
    categoria = (request.form.get("categoria") or "").strip() or None
    selected_tags = _resolve_selected_menu_tags(request.form.getlist("tag_ids"))
    raw_price = (request.form.get("price") or "").strip()

    if not name:
        flash("El nombre del plato es requerido.", "warning")
        return redirect(url_for("restaurante.menu"))

    try:
        price = Decimal(raw_price)
    except (InvalidOperation, TypeError):
        flash("Ingresá un precio válido.", "warning")
        return redirect(url_for("restaurante.menu"))

    if price <= 0:
        flash("El precio debe ser mayor a cero.", "warning")
        return redirect(url_for("restaurante.menu"))

    # Guardar nueva foto si se subió una
    foto_url = None
    foto_file = request.files.get("foto")
    if foto_file and foto_file.filename:
        foto_url = _save_img(foto_file, "menu", str(restaurant.id_restaurant))

    _upsert_menu_item(
        item,
        restaurant=restaurant,
        name=name,
        description=description,
        selected_tags=selected_tags,
        price=price,
        available=bool(item.disponibilidad),
        categoria=categoria,
        foto_url=foto_url,
    )
    db.session.commit()
    flash("Plato actualizado correctamente.", "success")
    return redirect(url_for("restaurante.menu"))


@restaurante_bp.route("/restaurante/menu/<uuid:item_id>/delete", methods=["POST"])
@login_required
def delete_menu_item(item_id):
    if not _admin_required():
        return redirect(url_for("usuario.home"))

    restaurant = _get_owned_restaurant()
    if restaurant is None:
        return redirect(url_for("restaurante.dashboard"))

    item = _get_owned_menu_item(restaurant, item_id)
    if item is None:
        flash("No se encontró el plato a eliminar.", "danger")
        return redirect(url_for("restaurante.menu"))

    db.session.delete(item)
    db.session.commit()
    flash("Plato eliminado correctamente.", "success")
    return redirect(url_for("restaurante.menu"))


@restaurante_bp.route("/restaurante/menu/<uuid:item_id>/availability", methods=["POST"])
@login_required
def update_menu_item_availability(item_id):
    if not _admin_required():
        return redirect(url_for("usuario.home"))

    restaurant = _get_owned_restaurant()
    if restaurant is None:
        return redirect(url_for("restaurante.dashboard"))

    item = _get_owned_menu_item(restaurant, item_id)
    if item is None:
        flash("No se encontró el plato para actualizar disponibilidad.", "danger")
        return redirect(url_for("restaurante.menu"))

    item.disponibilidad = request.form.get("available") == "1"
    db.session.commit()
    flash("Disponibilidad actualizada correctamente.", "success")
    return redirect(url_for("restaurante.menu"))



def _parse_horario(restaurant):
    """Devuelve la lista de slots de horario desde el JSON guardado en restaurant.horario."""
    if not restaurant.horario:
        return []
    try:
        data = json.loads(restaurant.horario)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


@restaurante_bp.route("/restaurante/profile")
@login_required
def profile_view():
    """Vista pública del perfil del restaurante (solo lectura)."""
    if not _admin_required():
        return redirect(url_for("usuario.home"))

    restaurant = _get_owned_restaurant()
    if restaurant is None:
        return redirect(url_for("restaurante.dashboard"))

    # Tags agrupados por categoría
    cuisine_tags  = [rt.tag.name for rt in restaurant.restaurant_tags if rt.tag and rt.tag.category == TagCategory.COMIDA]
    ambience_tags = [rt.tag.name for rt in restaurant.restaurant_tags if rt.tag and rt.tag.category == TagCategory.AMBIENTE]
    occasion_tags = [rt.tag.name for rt in restaurant.restaurant_tags if rt.tag and rt.tag.category == TagCategory.OCASION]

    horario = _parse_horario(restaurant)

    # Stats: reservas reales + mocks hasta implementar métricas completas
    from datetime import date
    hoy = date.today()
    reservas_mes = (
        db.session.query(Reserva)
        .filter(
            Reserva.id_restaurant == restaurant.id_restaurant,
            extract("month", Reserva.fecha_hora) == hoy.month,
            extract("year",  Reserva.fecha_hora) == hoy.year,
        )
        .count()
    )

    stats = {
        "reservas_mes":      reservas_mes,
        "ocupacion_pct":     78,   # TODO: calcular de reservas vs capacidad
        "platos_vistos":     len(restaurant.menus) * 12,  # TODO: implementar conteo real
        "tasa_retorno_pct":  34,   # TODO: implementar lógica de retorno
    }

    reviews_count = 0
    try:
        gallery = json.loads(restaurant.gallery_json or "[]")
    except (json.JSONDecodeError, TypeError):
        gallery = []

    return render_template(
        "restaurante/profile.html",
        restaurant=restaurant,
        cuisine_tags=cuisine_tags,
        ambience_tags=ambience_tags,
        occasion_tags=occasion_tags,
        horario=horario,
        stats=stats,
        reviews_count=reviews_count,
        gallery=gallery,
        active_admin_section="Perfil",
    )


@restaurante_bp.route("/restaurante/profile/edit")
@login_required
def edit_restaurant_profile():
    if not _admin_required():
        return redirect(url_for("usuario.home"))

    restaurant = _get_owned_restaurant()
    if restaurant is None:
        return redirect(url_for("restaurante.dashboard"))

    all_tags = db.session.query(Tag).order_by(Tag.category, Tag.name).all()
    cuisine_tags  = [tag for tag in all_tags if tag.category == TagCategory.COMIDA]
    ambience_tags = [tag for tag in all_tags if tag.category == TagCategory.AMBIENTE]
    occasion_tags = [tag for tag in all_tags if tag.category == TagCategory.OCASION]
    selected_tag_names = [item.tag.name for item in restaurant.restaurant_tags if item.tag]

    horario      = _parse_horario(restaurant)
    horario_json = restaurant.horario or "[]"

    try:
        gallery = json.loads(restaurant.gallery_json or "[]")
    except (json.JSONDecodeError, TypeError):
        gallery = []

    return render_template(
        "restaurante/edit_profile.html",
        restaurant=restaurant,
        cuisine_tags=cuisine_tags,
        ambience_tags=ambience_tags,
        occasion_tags=occasion_tags,
        selected_tag_names=selected_tag_names,
        horario=horario,
        horario_json=horario_json,
        gallery=gallery,
        active_admin_section="Perfil",
    )


@restaurante_bp.route("/restaurante/profile/edit", methods=["POST"])
@login_required
def update_restaurant_profile():
    if not _admin_required():
        return redirect(url_for("usuario.home"))

    restaurant = _get_owned_restaurant()
    if restaurant is None:
        return redirect(url_for("restaurante.dashboard"))

    # ── Texto ────────────────────────────────────────────────────────────────
    name          = (request.form.get("name")         or "").strip()
    address       = (request.form.get("address")      or "").strip()
    latitude      = request.form.get("latitude")
    longitude     = request.form.get("longitude")
    descripcion   = (request.form.get("descripcion")  or "").strip() or None
    precio_rango  = (request.form.get("precio_rango") or "").strip() or None
    capacidad_raw = (request.form.get("capacidad")    or "").strip()
    telefono      = (request.form.get("telefono")     or "").strip() or None
    sitio_web     = (request.form.get("sitio_web")    or "").strip() or None
    instagram     = (request.form.get("instagram")    or "").strip() or None
    horario_raw   = (request.form.get("horario")      or "[]").strip()
    cuisines      = [v.strip() for v in request.form.getlist("cuisines")  if v.strip()]
    ambience      = [v.strip() for v in request.form.getlist("ambience")  if v.strip()]
    occasions     = [v.strip() for v in request.form.getlist("occasions") if v.strip()]

    if not name:
        flash("El nombre del restaurante es requerido.", "warning")
        return redirect(url_for("restaurante.edit_restaurant_profile"))

    try:
        location_payload = resolve_location_payload(address, latitude, longitude)
    except ValueError:
        flash("No se pudo resolver la ubicación.", "warning")
        return redirect(url_for("restaurante.edit_restaurant_profile"))

    # ── Campos base ──────────────────────────────────────────────────────────
    restaurant.name      = name
    restaurant.address   = location_payload["address"]
    restaurant.latitude  = location_payload["latitude"]
    restaurant.longitude = location_payload["longitude"]

    if capacidad_raw.isdigit():
        restaurant.capacidad = int(capacidad_raw)

    # ── Horario (JSON en columna Text existente) ──────────────────────────
    try:
        restaurant.horario = json.dumps(json.loads(horario_raw), ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        pass

    # ── Campos nuevos (requieren migration.sql corrido primero) ──────────────
    restaurant.descripcion  = descripcion
    restaurant.precio_rango = precio_rango
    restaurant.telefono     = telefono
    restaurant.sitio_web    = sitio_web
    restaurant.instagram    = instagram

    # ── Foto de portada ───────────────────────────────────────────────────────
    cover_file = request.files.get("cover_photo")
    new_cover  = _save_img(cover_file, "covers", str(restaurant.id_restaurant))
    if new_cover:
        restaurant.cover_url = new_cover

    # ── Logo / avatar ─────────────────────────────────────────────────────────
    logo_file = request.files.get("logo_photo")
    new_logo  = _save_img(logo_file, "logos", str(restaurant.id_restaurant))
    if new_logo:
        restaurant.logo_url = new_logo

    # ── Galería ───────────────────────────────────────────────────────────────
    gallery_files = request.files.getlist("gallery_photos")
    current_gallery: list = []
    try:
        current_gallery = json.loads(restaurant.gallery_json or "[]")
    except (json.JSONDecodeError, TypeError):
        pass

    for gf in gallery_files:
        if len(current_gallery) >= _MAX_GALLERY:
            break
        path = _save_img(gf, "gallery", str(restaurant.id_restaurant))
        if path:
            current_gallery.append(path)

    restaurant.gallery_json = json.dumps(current_gallery, ensure_ascii=False)

    # ── Sincronizar ubicación al owner (solo coordenadas, NO el nombre) ─────
    current_user.address   = location_payload["address"]
    current_user.latitude  = location_payload["latitude"]
    current_user.longitude = location_payload["longitude"]

    # ── Tags ──────────────────────────────────────────────────────────────────
    db.session.query(RestaurantTags).filter(
        RestaurantTags.id_restaurant == restaurant.id_restaurant
    ).delete(synchronize_session=False)

    selected_tags = (
        db.session.query(Tag)
        .filter(
            or_(
                and_(Tag.category == TagCategory.COMIDA,   Tag.name.in_(cuisines)),
                and_(Tag.category == TagCategory.AMBIENTE, Tag.name.in_(ambience)),
                and_(Tag.category == TagCategory.OCASION,  Tag.name.in_(occasions)),
            )
        )
        .all()
    )
    for tag in selected_tags:
        db.session.add(RestaurantTags(id_restaurant=restaurant.id_restaurant, id_tag=tag.id_tag))

    db.session.commit()
    flash("Perfil actualizado correctamente.", "success")
    return redirect(url_for("restaurante.profile_view"))


@restaurante_bp.route("/restaurante/security")
@login_required
def security():
    if not _admin_required():
        return redirect(url_for("usuario.profile"))
    restaurant = _get_owned_restaurant()
    return render_template(
        "restaurante/cuenta_seguridad.html",
        restaurant=restaurant,
        active_admin_section="Cuenta",
    )


@restaurante_bp.route("/restaurante/security/change-password", methods=["POST"])
@login_required
def change_password():
    if not _admin_required():
        return redirect(url_for("usuario.profile"))

    current_pw  = (request.form.get("current_password") or "").strip()
    new_pw      = (request.form.get("new_password") or "").strip()
    confirm_pw  = (request.form.get("confirm_password") or "").strip()

    if not all([current_pw, new_pw, confirm_pw]):
        flash("Completá todos los campos.", "warning")
        return redirect(url_for("restaurante.security"))

    if new_pw != confirm_pw:
        flash("Las contraseñas nuevas no coinciden.", "warning")
        return redirect(url_for("restaurante.security"))

    if len(new_pw) <= 4:
        flash("La contraseña debe tener más de 4 caracteres.", "warning")
        return redirect(url_for("restaurante.security"))

    if not current_user.check_password(current_pw):
        flash("La contraseña actual es incorrecta.", "danger")
        return redirect(url_for("restaurante.security"))

    current_user.password = new_pw
    db.session.commit()
    flash("Contraseña actualizada correctamente.", "success")
    return redirect(url_for("restaurante.security"))


@restaurante_bp.route("/restaurante/delete", methods=["POST"])
@login_required
def delete_restaurant():
    if not _admin_required():
        return redirect(url_for("usuario.profile"))

    restaurant = _get_owned_restaurant()
    if restaurant is None:
        flash("No se encontró tu restaurante.", "danger")
        return redirect(url_for("restaurante.dashboard"))

    confirm_name = (request.form.get("confirm_name") or "").strip()
    if confirm_name != restaurant.name:
        flash("El nombre ingresado no coincide. No se realizaron cambios.", "danger")
        return redirect(url_for("restaurante.profile_view"))

    try:
        db.session.delete(restaurant)
        db.session.commit()
        flash("Tu restaurante fue eliminado de Morfi correctamente.", "info")
    except Exception:
        db.session.rollback()
        flash("No se pudo eliminar el restaurante. Intentá de nuevo.", "danger")
        return redirect(url_for("restaurante.profile_view"))

    return redirect(url_for("usuario.home"))


@restaurante_bp.route("/restaurante/users/<uuid:user_id>/delete", methods=["POST"])
@login_required
def delete_user(user_id):
    if not _admin_required():
        return redirect(url_for("usuario.profile"))

    user = db.session.get(User, user_id)
    if user is None:
        return redirect(url_for("restaurante.dashboard"))

    if str(user.user_id) == current_user.get_id():
        return redirect(url_for("restaurante.dashboard"))

    username = user.username
    db.session.delete(user)
    db.session.commit()
    return redirect(url_for("restaurante.dashboard"))