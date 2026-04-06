from flask import Blueprint, render_template, request
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload

from app.database import db
from app.location import haversine_km, parse_float
from app.models.restaurant import Restaurant
from app.models.restaurant_tags import RestaurantTags

home_bp = Blueprint("home", __name__)



@home_bp.route('/home')
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
        'home.html',
        restaurants=restaurant_cards,
        nearby_active=nearby_active,
        user_lat=default_user_lat,
        user_lng=default_user_lng,
    )
