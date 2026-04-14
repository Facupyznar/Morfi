from datetime import datetime, timedelta, date

from flask import jsonify, render_template, request, redirect, url_for, flash
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload

from app.database import db
from app.location import haversine_km, parse_float
from app.models.restaurant import Restaurant
from app.models.restaurant_tags import RestaurantTags
from app.models.reserva import Reserva
from app.models.enums import ReservaStatus
from app.models.menu import Menu
from app.routes.usuario import usuario_bp


# ── Helpers ──────────────────────────────────────────────────────

def _ocupados_slot(restaurant_id, fecha: date, hora_str: str) -> int:
    """Suma comensales de reservas CONFIRMADAS en esa franja de 30 min."""
    hora = datetime.strptime(hora_str, "%H:%M").time()
    inicio = datetime.combine(fecha, hora)
    fin    = inicio + timedelta(minutes=60)

    result = (
        db.session.query(db.func.coalesce(db.func.sum(Reserva.cant_personas), 0))
        .filter(
            Reserva.id_restaurant == restaurant_id,
            Reserva.estado_reserva == ReservaStatus.CONFIRMADA,
            Reserva.fecha_hora >= inicio,
            Reserva.fecha_hora <  fin,
        )
        .scalar()
    )
    return int(result or 0)


def _parse_horario_restaurant(restaurant):
    import json
    if not restaurant.horario:
        return []
    try:
        data = json.loads(restaurant.horario)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _slots_para_fecha(restaurant, fecha: date):
    """
    Devuelve lista de strings 'HH:MM' disponibles para la fecha,
    según el horario del restaurante (slots cada 30 min).

    Las keys guardadas en el JSON son: 'lun_jue', 'vie', 'sab', 'dom'.
    weekday(): 0=lun, 1=mar, 2=mie, 3=jue, 4=vie, 5=sab, 6=dom
    """
    horario = _parse_horario_restaurant(restaurant)

    # Mapeo weekday → key del JSON de horario
    dia = fecha.weekday()
    if dia <= 3:
        key_buscada = "lun_jue"
    elif dia == 4:
        key_buscada = "vie"
    elif dia == 5:
        key_buscada = "sab"
    else:
        key_buscada = "dom"

    apertura = cierre = None
    for entry in horario:
        if entry.get("key") == key_buscada and entry.get("active"):
            apertura = entry.get("open",  "12:00")
            cierre   = entry.get("close", "23:00")
            break

    # Fallback: si el restaurante no configuró horario, usar valores por defecto
    if not apertura:
        if horario:
            # Tiene horario pero este día está cerrado
            return []
        # No tiene horario cargado → slots por defecto
        apertura, cierre = "12:00", "23:00"

    fmt   = "%H:%M"
    cur   = datetime.strptime(apertura, fmt)
    end   = datetime.strptime(cierre,   fmt)
    # Manejar cierre de medianoche (00:00 significa fin del día)
    if end <= cur:
        end = datetime.strptime("23:30", fmt)

    slots = []
    while cur <= end:
        slots.append(cur.strftime(fmt))
        cur += timedelta(minutes=60)
    return slots


# ── Rutas ─────────────────────────────────────────────────────────

@usuario_bp.route('/home')
@login_required
def home():
    try:
        user_lat = parse_float(request.args.get("user_lat"))
        user_lng = parse_float(request.args.get("user_lng"))
    except ValueError:
        user_lat = None
        user_lng = None
    nearby_active = user_lat is not None and user_lng is not None

    if not nearby_active and getattr(current_user, "latitude", None) is not None and getattr(current_user, "longitude", None) is not None:
        default_user_lat = float(current_user.latitude)
        default_user_lng = float(current_user.longitude)
    else:
        default_user_lat = user_lat
        default_user_lng = user_lng

    distance_user_lat = default_user_lat
    distance_user_lng = default_user_lng

    restaurants = (
        db.session.query(Restaurant)
        .options(joinedload(Restaurant.restaurant_tags).joinedload(RestaurantTags.tag))
        .all()
    )
    restaurant_cards = []

    for restaurant in restaurants:
        distance_km = None
        if distance_user_lat is not None and distance_user_lng is not None:
            distance_km = haversine_km(
                distance_user_lat, distance_user_lng,
                restaurant.latitude, restaurant.longitude,
            )
        if nearby_active and distance_km is not None and distance_km > 5:
            continue

        tag_names = [
            rt.tag.name for rt in restaurant.restaurant_tags if rt.tag is not None
        ]
        restaurant_cards.append({
            "id":             str(restaurant.id_restaurant),
            "name":           restaurant.name,
            "tags":           tag_names[:3],
            "distance":       round(distance_km, 1) if distance_km is not None else None,
            "distance_label": f"{distance_km:.1f} km de vos" if distance_km is not None else restaurant.address,
            "price_range":    "$$",
            "rating":         float(restaurant.puntaje or 0),
            "match_percent":  95,
            "image_url":      "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?q=80&w=800",
        })

    if user_lat is not None and user_lng is not None:
        restaurant_cards.sort(key=lambda r: r["distance"] if r["distance"] is not None else 999999)

    return render_template(
        'usuario/home.html',
        restaurants=restaurant_cards,
        nearby_active=nearby_active,
        user_lat=default_user_lat,
        user_lng=default_user_lng,
    )


@usuario_bp.route("/restaurante/<restaurant_id>")
@login_required
def restaurant_detail(restaurant_id):
    import json
    from flask import url_for as _url_for

    restaurant_record = (
        db.session.query(Restaurant)
        .options(joinedload(Restaurant.restaurant_tags).joinedload(RestaurantTags.tag))
        .filter_by(id_restaurant=restaurant_id)
        .first_or_404()
    )
    tag_names = [rt.tag.name for rt in restaurant_record.restaurant_tags if rt.tag is not None]
    menu_items = (
        db.session.query(Menu)
        .filter_by(id_restaurant=restaurant_id)
        .order_by(Menu.categoria, Menu.nombre)
        .all()
    )

    # Horario: parsear el JSON guardado por el socio
    horario_list = _parse_horario_restaurant(restaurant_record)

    # Galería: parsear el JSON de paths
    try:
        gallery = json.loads(restaurant_record.gallery_json or "[]")
    except (json.JSONDecodeError, TypeError):
        gallery = []

    # Imagen de portada: usar la subida por el socio, o fallback genérico
    if restaurant_record.cover_url:
        image_url = _url_for("static", filename=restaurant_record.cover_url)
    else:
        image_url = "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?q=80&w=800"

    # Logo
    logo_url = _url_for("static", filename=restaurant_record.logo_url) if restaurant_record.logo_url else None

    restaurant_data = {
        "id":           str(restaurant_record.id_restaurant),
        "name":         restaurant_record.name,
        "rating":       round(float(restaurant_record.puntaje or 0), 1),
        "tags":         tag_names[:3],
        "image_url":    image_url,
        "logo_url":     logo_url,
        "address":      restaurant_record.address or "",
        "distance_label": restaurant_record.address or "",
        "horario":      horario_list,
        "descripcion":  restaurant_record.descripcion or "",
        "precio_rango": restaurant_record.precio_rango or "",
        "telefono":     restaurant_record.telefono or "",
        "sitio_web":    restaurant_record.sitio_web or "",
        "instagram":    restaurant_record.instagram or "",
        "capacidad":    restaurant_record.capacidad or 0,
        "gallery":      gallery,
        "latitude":     float(restaurant_record.latitude) if restaurant_record.latitude else None,
        "longitude":    float(restaurant_record.longitude) if restaurant_record.longitude else None,
    }
    return render_template(
        "usuario/restaurant_detail.html",
        restaurant=restaurant_data,
        menu_items=menu_items,
    )


# ── Wizard de reserva ─────────────────────────────────────────────

@usuario_bp.route("/restaurante/<restaurant_id>/reserva")
@login_required
def reserva_wizard(restaurant_id):
    restaurant_record = (
        db.session.query(Restaurant)
        .options(joinedload(Restaurant.restaurant_tags).joinedload(RestaurantTags.tag))
        .filter_by(id_restaurant=restaurant_id)
        .first_or_404()
    )
    tag_names = [rt.tag.name for rt in restaurant_record.restaurant_tags if rt.tag is not None]
    restaurant_data = {
        "id":          str(restaurant_record.id_restaurant),
        "name":        restaurant_record.name,
        "tags":        tag_names[:3],
        "price_range": "$$",
        "address":     restaurant_record.address or "",
        "capacidad":   restaurant_record.capacidad or 0,
    }
    return render_template("usuario/reserva_wizard.html", restaurant=restaurant_data)


# ── API: disponibilidad de slots para una fecha ───────────────────

@usuario_bp.route("/restaurante/<restaurant_id>/disponibilidad")
@login_required
def disponibilidad(restaurant_id):
    """
    GET /restaurante/<id>/disponibilidad?fecha=YYYY-MM-DD
    Devuelve JSON con slots disponibles y ocupación de cada uno.
    """
    restaurant_record = db.session.query(Restaurant).filter_by(
        id_restaurant=restaurant_id
    ).first_or_404()

    fecha_param = request.args.get("fecha")
    try:
        fecha = date.fromisoformat(fecha_param)
    except (TypeError, ValueError):
        return jsonify({"error": "Fecha inválida"}), 400

    if fecha < date.today():
        return jsonify({"error": "No podés reservar en fechas pasadas"}), 400

    capacidad = restaurant_record.capacidad or 0
    slots_raw = _slots_para_fecha(restaurant_record, fecha)

    slots = []
    for hora in slots_raw:
        ocupados    = _ocupados_slot(restaurant_record.id_restaurant, fecha, hora)
        disponibles = max(capacidad - ocupados, 0)
        slots.append({
            "hora":        hora,
            "ocupados":    ocupados,
            "disponibles": disponibles,
            "disponible":  disponibles > 0,
            "pct":         round((ocupados / capacidad) * 100) if capacidad > 0 else 0,
        })

    return jsonify({
        "restaurante": restaurant_record.name,
        "fecha":       fecha_param,
        "capacidad":   capacidad,
        "slots":       slots,
    })


# ── POST: crear reserva ───────────────────────────────────────────

@usuario_bp.route("/restaurante/<restaurant_id>/reservar", methods=["POST"])
@login_required
def crear_reserva(restaurant_id):
    restaurant_record = db.session.query(Restaurant).filter_by(
        id_restaurant=restaurant_id
    ).first_or_404()

    fecha_str = request.form.get("fecha", "").strip()
    hora_str  = request.form.get("hora",  "").strip()
    comensales = request.form.get("comensales", "2").strip()

    # Validar campos obligatorios
    if not fecha_str or not hora_str:
        flash("Por favor completá la fecha y hora.", "warning")
        return redirect(url_for("usuario.reserva_wizard", restaurant_id=restaurant_id))

    try:
        comensales = int(comensales)
        if comensales < 1 or comensales > 20:
            raise ValueError
    except ValueError:
        flash("Cantidad de comensales inválida.", "warning")
        return redirect(url_for("usuario.reserva_wizard", restaurant_id=restaurant_id))

    try:
        fecha_hora = datetime.strptime(f"{fecha_str} {hora_str}", "%Y-%m-%d %H:%M")
    except ValueError:
        flash("Fecha u hora inválida.", "warning")
        return redirect(url_for("usuario.reserva_wizard", restaurant_id=restaurant_id))

    if fecha_hora < datetime.now():
        flash("No podés reservar en fechas pasadas.", "warning")
        return redirect(url_for("usuario.reserva_wizard", restaurant_id=restaurant_id))

    # Verificar disponibilidad
    capacidad = restaurant_record.capacidad or 0
    ocupados  = _ocupados_slot(restaurant_record.id_restaurant, fecha_hora.date(), hora_str)
    if capacidad > 0 and (ocupados + comensales) > capacidad:
        flash("No hay suficiente disponibilidad para ese horario. Elegí otro.", "warning")
        return redirect(url_for("usuario.reserva_wizard", restaurant_id=restaurant_id))

    # Crear reserva
    try:
        nueva = Reserva(
            user_id        = current_user.user_id,
            id_restaurant  = restaurant_record.id_restaurant,
            fecha_hora     = fecha_hora,
            cant_personas  = comensales,
            estado_reserva = ReservaStatus.CONFIRMADA,
        )
        db.session.add(nueva)
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("No se pudo crear la reserva. Intentá de nuevo.", "danger")
        return redirect(url_for("usuario.reserva_wizard", restaurant_id=restaurant_id))

    return redirect(url_for(
        "usuario.reserva_confirmada",
        restaurant_id = restaurant_id,
        id_reserva    = str(nueva.id_reserva),
    ))


# ── Pantalla de éxito ─────────────────────────────────────────────

@usuario_bp.route("/reserva/<id_reserva>/confirmada")
@login_required
def reserva_confirmada(id_reserva):
    reserva = Reserva.query.filter_by(
        id_reserva = id_reserva,
        user_id    = current_user.user_id,
    ).first_or_404()

    return render_template(
        "usuario/reserva_confirmada.html",
        reserva    = reserva,
        restaurant = reserva.restaurant,
    )