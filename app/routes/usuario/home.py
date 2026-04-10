from flask import render_template, request,redirect ,url_for, flash, abort
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload

from app.database import db
from app.location import haversine_km, parse_float
from app.models.restaurant import Restaurant
from app.models.restaurant_tags import RestaurantTags
from app.models.reserva import Reserva
from app.models.menu import Menu
from app.routes.usuario import usuario_bp



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
                distance_user_lat,
                distance_user_lng,
                restaurant.latitude,
                restaurant.longitude,
            )

        if nearby_active and distance_km is not None:
            if distance_km > 5:
                continue

        tag_names = [
            restaurant_tag.tag.name
            for restaurant_tag in restaurant.restaurant_tags
            if restaurant_tag.tag is not None
        ]

        restaurant_cards.append(
            {
                "id": str(restaurant.id_restaurant),
                "name": restaurant.name,
                "tags": tag_names[:3],
                "distance": round(distance_km, 1) if distance_km is not None else None,
                "distance_label": f"{distance_km:.1f} km de vos" if distance_km is not None else restaurant.address,
                "price_range": "$$",
                "rating": float(restaurant.puntaje or 0),
                "match_percent": 95,
                "image_url": "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?q=80&w=800",
            }
        )

    if user_lat is not None and user_lng is not None:
        restaurant_cards.sort(key=lambda item: item["distance"] if item["distance"] is not None else 999999)

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
    restaurant_record = (
        db.session.query(Restaurant)
        .options(joinedload(Restaurant.restaurant_tags).joinedload(RestaurantTags.tag))
        .filter_by(id_restaurant=restaurant_id)
        .first_or_404()
    )

    tag_names = [
        rt.tag.name
        for rt in restaurant_record.restaurant_tags
        if rt.tag is not None
    ]

    menu_items = (
        db.session.query(Menu)
        .filter_by(id_restaurant=restaurant_id)
        .order_by(Menu.categoria, Menu.nombre)
        .all()
    )

    restaurant_data = {
        "id":             str(restaurant_record.id_restaurant),
        "name":           restaurant_record.name,
        "rating":         round(float(restaurant_record.puntaje or 0), 1),
        "tags":           tag_names[:3],
        "image_url":      "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?q=80&w=800",
        "distance_label": restaurant_record.address or "",
        "address":        restaurant_record.address or "",
        "horario":        "",
        "latitude":       float(restaurant_record.latitude) if restaurant_record.latitude else None,
        "longitude":      float(restaurant_record.longitude) if restaurant_record.longitude else None,
    }

    return render_template(
        "usuario/restaurant_detail.html",
        restaurant=restaurant_data,
        menu_items=menu_items,
    )
 
 
@usuario_bp.route("/restaurante/<restaurant_id>/reservar", methods=["POST"])
@login_required
def crear_reserva(restaurant_id):
    restaurant_record = db.session.query(Restaurant).filter_by(
        id_restaurant=restaurant_id
    ).first_or_404()

    fecha      = request.form.get("fecha")
    hora       = request.form.get("hora")
    comensales = request.form.get("comensales", 2)

    if not fecha or not hora:
        flash("Por favor completá la fecha y hora.", "warning")
        return redirect(url_for("usuario.restaurant_detail", restaurant_id=restaurant_id))

    try:
        nueva = Reserva(
            user_id=current_user.user_id,
            restaurant_id=restaurant_id,
            fecha=fecha,
            hora=hora,
            comensales=int(comensales),
        )
        db.session.add(nueva)
        db.session.commit()
        flash("¡Reserva confirmada!", "success")
    except Exception as e:
        db.session.rollback()
        flash("No se pudo crear la reserva. Intentá de nuevo.", "danger")

    return redirect(url_for("usuario.restaurant_detail", restaurant_id=restaurant_id))

@usuario_bp.route("/restaurante/<restaurant_id>/reserva")
@login_required
def reserva_wizard(restaurant_id):
    """Wizard de reserva en 3 pasos (Fecha → Hora → Confirmación)."""
    restaurant_record = (
        db.session.query(Restaurant)
        .options(joinedload(Restaurant.restaurant_tags).joinedload(RestaurantTags.tag))
        .filter_by(id_restaurant=restaurant_id)
        .first_or_404()
    )
 
    tag_names = [
        rt.tag.name
        for rt in restaurant_record.restaurant_tags
        if rt.tag is not None
    ]
 
    restaurant_data = {
        "id":          str(restaurant_record.id_restaurant),
        "name":        restaurant_record.name,
        "tags":        tag_names[:3],
        "price_range": "$$",
        "address":     restaurant_record.address or "",
    }
 
    return render_template("usuario/reserva_wizard.html", restaurant=restaurant_data)
