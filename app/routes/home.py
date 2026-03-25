from flask import Blueprint, render_template
from flask_login import login_required


home_bp = Blueprint("home", __name__)



@home_bp.route('/home')
@login_required
def index():
    # Datos de prueba basados en tu imagen
    dummy_restaurants = [
        {
            "name": "La Parrilla Criolla",
            "cuisine": "Parrilla Argentina",
            "distance": 0.8,
            "price_range": "$$",
            "rating": 4.8,
            "match_percent": 95,
            "amigos_count": 12,
            "trending": True,
            "image_url": "https://images.unsplash.com/photo-1544025162-d76694265947?q=80&w=800"
        },
        {
            "name": "Don Julio",
            "cuisine": "Parrilla Premium",
            "distance": 2.3,
            "price_range": "$$$",
            "rating": 4.9,
            "match_percent": 88,
            "amigos_count": 8,
            "trending": False,
            "image_url": "https://images.unsplash.com/photo-1555939594-58d7cb561ad1?q=80&w=800"
        }
    ]
    return render_template('index.html', restaurants=dummy_restaurants)