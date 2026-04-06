import uuid
from collections import defaultdict

from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from app.database import db
from app.models.enums import TagCategory
from app.models.reserva import Reserva
from app.models.restaurant import Restaurant
from app.models.review import Review
from app.models.tag import Tag
from app.models.user import Role, User


system_bp = Blueprint("system", __name__)


def _system_required():
    role_value = getattr(getattr(current_user, "rol", None), "value", None)
    return role_value == Role.ADMIN_GLOBAL.value


def _require_system_access():
    if _system_required():
        return None
    return redirect(url_for("profile.profile"))


def _initials_from_name(value, fallback="U"):
    raw_value = (value or "").strip()
    if not raw_value:
        return fallback
    parts = [part for part in raw_value.split() if part]
    if len(parts) >= 2:
        return f"{parts[0][0]}{parts[1][0]}".upper()
    return raw_value[:2].upper()


def _format_datetime_label(value):
    if not value:
        return "Sin fecha"
    return value.strftime("%d %b %Y").lower()


def _restaurant_status_meta(restaurant):
    raw_status = getattr(getattr(restaurant, "estado", None), "value", None) or "inactivo"
    labels = {
        "activo": "Activo",
        "inactivo": "Inactivo",
        "suspendido": "Suspendido",
    }
    return raw_status, labels.get(raw_status, raw_status.replace("_", " ").title())


def _category_title(category_value):
    labels = {
        TagCategory.COMIDA.value: "Tipo de cocina",
        TagCategory.AMBIENTE.value: "Ambiente",
        TagCategory.DIETA.value: "Restricciones",
        TagCategory.OCASION.value: "Ocasiones",
        TagCategory.OTRO.value: "Otros",
    }
    return labels.get(category_value, category_value.replace("_", " ").title())


@system_bp.route("/system")
@login_required
def index():
    denied_response = _require_system_access()
    if denied_response is not None:
        return denied_response
    return redirect(url_for("system.restaurants"))


@system_bp.route("/system/restaurants")
@login_required
def restaurants():
    denied_response = _require_system_access()
    if denied_response is not None:
        return denied_response

    restaurant_records = db.session.query(Restaurant).order_by(Restaurant.name.asc()).all()
    selected_restaurant_id = request.args.get("restaurant_id", "").strip()
    try:
        normalized_selected_id = uuid.UUID(selected_restaurant_id) if selected_restaurant_id else None
    except ValueError:
        normalized_selected_id = None

    restaurants_payload = []
    selected_restaurant = None

    for restaurant in restaurant_records:
        status_slug, status_label = _restaurant_status_meta(restaurant)
        cuisine_tag = next(
            (
                relation.tag.name
                for relation in getattr(restaurant, "restaurant_tags", [])
                if relation.tag and relation.tag.category == TagCategory.COMIDA
            ),
            None,
        )
        owner = getattr(restaurant, "owner", None)
        payload = {
            "id": str(restaurant.id_restaurant),
            "name": restaurant.name,
            "logo_url": url_for("static", filename=owner.foto_perfil) if getattr(owner, "foto_perfil", None) else None,
            "address": restaurant.address,
            "requested_at_label": "Sin fecha",
            "status_slug": status_slug,
            "status_label": status_label,
            "category_name": cuisine_tag,
            "phone": None,
            "email": getattr(owner, "email", None),
            "documents": [],
            "verification_checklist": [
                {"label": "Dirección configurada", "checked": bool(restaurant.address)},
                {"label": "Ubicación geográfica cargada", "checked": restaurant.latitude is not None and restaurant.longitude is not None},
                {"label": "Contacto del socio disponible", "checked": bool(getattr(owner, "email", None))},
                {"label": "Tags del restaurante asignados", "checked": any(relation.tag for relation in getattr(restaurant, "restaurant_tags", []))},
            ],
            "href": url_for("system.restaurants", restaurant_id=restaurant.id_restaurant),
        }
        restaurants_payload.append(payload)
        if normalized_selected_id and restaurant.id_restaurant == normalized_selected_id:
            selected_restaurant = payload

    if selected_restaurant is None and restaurants_payload:
        selected_restaurant = restaurants_payload[0]

    return render_template(
        "system/system_restaurants.html",
        restaurants=restaurants_payload,
        selected_restaurant=selected_restaurant,
        verification_checklist=selected_restaurant["verification_checklist"] if selected_restaurant else [],
        active_system_section="Restaurantes",
    )


@system_bp.route("/system/reviews")
@login_required
def reviews():
    denied_response = _require_system_access()
    if denied_response is not None:
        return denied_response

    review_records = (
        db.session.query(Review)
        .join(Reserva, Review.id_reserva == Reserva.id_reserva)
        .join(Restaurant, Reserva.id_restaurant == Restaurant.id_restaurant)
        .join(User, Reserva.user_id == User.user_id)
        .order_by(Reserva.fecha_hora.desc())
        .all()
    )

    reviews_payload = []
    for review in review_records:
        reservation = review.reserva
        user = reservation.user if reservation else None
        restaurant = reservation.restaurant if reservation else None
        reviews_payload.append(
            {
                "id": str(review.id_review),
                "user_name": getattr(user, "name", None) or getattr(user, "username", "Usuario"),
                "user_initials": _initials_from_name(getattr(user, "name", None) or getattr(user, "username", "")),
                "restaurant_name": getattr(restaurant, "name", "Restaurante"),
                "comment": review.comentario or "Sin comentario.",
                "reason_label": "Sin reportes",
                "report_count": 0,
                "created_at_label": _format_datetime_label(getattr(reservation, "fecha_hora", None)),
                "status_slug": "published",
                "status_label": "Publicada",
            }
        )

    return render_template(
        "system/system_reviews.html",
        reviews=reviews_payload,
        pending_reviews_count=0,
        review_filters=[
            {"slug": "all", "label": "Todas", "active": True},
            {"slug": "pending", "label": "Pendientes de revisión", "active": False},
            {"slug": "removed", "label": "Eliminadas", "active": False},
        ],
        active_system_section="Reseñas",
    )


@system_bp.route("/system/tags")
@login_required
def tags():
    denied_response = _require_system_access()
    if denied_response is not None:
        return denied_response

    selected_category = (request.args.get("category") or "").strip().lower()
    tag_records = db.session.query(Tag).order_by(Tag.category.asc(), Tag.name.asc()).all()
    grouped_tags = defaultdict(list)

    for tag in tag_records:
        category_value = getattr(getattr(tag, "category", None), "value", None) or TagCategory.OTRO.value
        grouped_tags[category_value].append(
            {
                "id": str(tag.id_tag),
                "name": tag.name,
                "restaurant_count": len(getattr(tag, "restaurant_tags", [])),
                "user_count": len(getattr(tag, "user_tags", [])),
                "active": True,
            }
        )

    available_categories = sorted(grouped_tags.keys(), key=lambda value: _category_title(value))
    if not selected_category or selected_category not in grouped_tags:
        selected_category = available_categories[0] if available_categories else TagCategory.COMIDA.value

    categories_payload = []
    for category_value in available_categories:
        tags_in_category = grouped_tags[category_value]
        categories_payload.append(
            {
                "slug": category_value,
                "name": _category_title(category_value),
                "tag_count": len(tags_in_category),
                "restaurant_count": sum(tag["restaurant_count"] for tag in tags_in_category),
                "active": category_value == selected_category,
                "href": url_for("system.tags", category=category_value),
            }
        )

    return render_template(
        "system/system_tags.html",
        tag_categories=categories_payload,
        selected_category_name=_category_title(selected_category),
        tags=grouped_tags.get(selected_category, []),
        active_system_section="Tags",
    )


@system_bp.route("/system/users")
@login_required
def users():
    denied_response = _require_system_access()
    if denied_response is not None:
        return denied_response

    reservations_count_subquery = (
        db.session.query(
            Reserva.user_id.label("user_id"),
            func.count(Reserva.id_reserva).label("reservations_count"),
        )
        .group_by(Reserva.user_id)
        .subquery()
    )
    reviews_count_subquery = (
        db.session.query(
            Reserva.user_id.label("user_id"),
            func.count(Review.id_review).label("reviews_count"),
        )
        .join(Review, Review.id_reserva == Reserva.id_reserva)
        .group_by(Reserva.user_id)
        .subquery()
    )

    user_rows = (
        db.session.query(
            User,
            func.coalesce(reservations_count_subquery.c.reservations_count, 0),
            func.coalesce(reviews_count_subquery.c.reviews_count, 0),
        )
        .outerjoin(reservations_count_subquery, reservations_count_subquery.c.user_id == User.user_id)
        .outerjoin(reviews_count_subquery, reviews_count_subquery.c.user_id == User.user_id)
        .order_by(User.name.asc().nullslast(), User.username.asc())
        .all()
    )

    users_payload = []
    for user, reservations_count, reviews_count in user_rows:
        role_value = getattr(getattr(user, "rol", None), "value", None)
        display_name = user.name or user.username
        status_slug = "active" if getattr(user, "is_active", True) else "suspended"
        status_label = "Activo" if status_slug == "active" else "Suspendido"
        users_payload.append(
            {
                "id": str(user.user_id),
                "name": display_name,
                "email": user.email,
                "joined_at_label": f"Rol: {(role_value or 'comensal').replace('_', ' ').title()}",
                "reservations_count": int(reservations_count or 0),
                "reviews_count": int(reviews_count or 0),
                "status_slug": status_slug,
                "status_label": status_label,
                "initials": _initials_from_name(display_name, "US"),
                "can_manage": str(user.user_id) != current_user.get_id(),
            }
        )

    suspended_users = sum(1 for user in users_payload if user["status_slug"] == "suspended")

    return render_template(
        "system/system_users.html",
        users=users_payload,
        user_stats={
            "total_users": len(users_payload),
            "active_users": len(users_payload) - suspended_users,
            "suspended_users": suspended_users,
        },
        user_filters=[
            {"slug": "all", "label": "Todos", "active": True},
            {"slug": "active", "label": "Activos", "active": False},
            {"slug": "suspended", "label": "Suspendidos", "active": False},
        ],
        active_system_section="Usuarios",
    )


@system_bp.route("/system/users/<uuid:user_id>/delete", methods=["POST"])
@login_required
def delete_user(user_id):
    denied_response = _require_system_access()
    if denied_response is not None:
        return denied_response

    user = db.session.get(User, user_id)
    if user is None:
        return redirect(url_for("system.users"))

    if str(user.user_id) == current_user.get_id():
        return redirect(url_for("system.users"))

    username = user.username
    db.session.delete(user)
    db.session.commit()
    return redirect(url_for("system.users"))


@system_bp.route("/system/users/<uuid:user_id>/toggle-suspension", methods=["POST"])
@login_required
def toggle_user_suspension(user_id):
    denied_response = _require_system_access()
    if denied_response is not None:
        return denied_response

    user = db.session.get(User, user_id)
    if user is None:
        return redirect(url_for("system.users"))

    if str(user.user_id) == current_user.get_id():
        return redirect(url_for("system.users"))

    user.is_active = not bool(getattr(user, "is_active", True))
    db.session.commit()

    return redirect(url_for("system.users"))
