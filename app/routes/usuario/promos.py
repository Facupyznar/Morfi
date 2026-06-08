"""Vista de consumo del comensal: Ofertas & Beneficios de sus restaurantes favoritos."""

from flask import render_template
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload

from app.database import db
from app.helpers.promos import beneficios_con_progreso, ofertas_vigentes
from app.models.user_favorites import UserFavorites
from app.routes.usuario import usuario_bp


@usuario_bp.route("/ofertas")
@login_required
def ofertas():
    favoritos = (
        db.session.query(UserFavorites)
        .options(joinedload(UserFavorites.restaurant))
        .filter(UserFavorites.user_id == current_user.user_id)
        .order_by(UserFavorites.fecha_agregado.desc())
        .all()
    )

    restaurantes = []
    total_ofertas = 0
    total_beneficios = 0
    for favorito in favoritos:
        restaurant = favorito.restaurant
        if restaurant is None:
            continue
        ofertas_rest = ofertas_vigentes(restaurant.id_restaurant)
        beneficios_rest = beneficios_con_progreso(restaurant.id_restaurant, current_user.user_id)
        if not ofertas_rest and not beneficios_rest:
            continue
        total_ofertas += len(ofertas_rest)
        total_beneficios += len(beneficios_rest)
        restaurantes.append(
            {
                "id": str(restaurant.id_restaurant),
                "name": restaurant.name,
                "cover_url": restaurant.cover_url,
                "ofertas": ofertas_rest,
                "beneficios": beneficios_rest,
            }
        )

    return render_template(
        "usuario/ofertas.html",
        restaurantes=restaurantes,
        total_ofertas=total_ofertas,
        total_beneficios=total_beneficios,
    )
