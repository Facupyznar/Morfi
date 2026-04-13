from flask import Blueprint, render_template
from flask_login import login_required, current_user
from datetime import date
restaurant_bp = Blueprint("restaurant", __name__)

from datetime import date, datetime
from collections import defaultdict

DIAS_ES = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
MESES_ES = [
    "", "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
]

@restaurant_bp.route("/panel/dashboard")
@login_required
def dashboard():
    # ── Obtener restaurante del usuario actual ──────────────────────────
    # Ajustá según tu modelo (puede ser current_user.restaurant o una query)
    restaurant_record = (
        db.session.query(Restaurant)
        .filter_by(owner_id=current_user.user_id)
        .first_or_404()
    )
 
    restaurant_data = {
        "id":   str(restaurant_record.id_restaurant),
        "name": restaurant_record.name,
    }
 
    # ── Fecha de hoy ────────────────────────────────────────────────────
    hoy = date.today()
    dia_semana = DIAS_ES[hoy.weekday()]
    today_label = f"{dia_semana} {hoy.day} de {MESES_ES[hoy.month]}"
 
    # ── Reservas de hoy ─────────────────────────────────────────────────
    reservas_db = (
        db.session.query(Reserva)
        .filter_by(restaurant_id=restaurant_record.id_restaurant)
        .filter(Reserva.fecha == hoy.isoformat())
        .order_by(Reserva.hora)
        .limit(10)
        .all()
    )
 
    reservas_hoy = []
    for r in reservas_db:
        user = db.session.query(User).filter_by(user_id=r.user_id).first()
        nombre = user.name if user else "Cliente"
        reservas_hoy.append({
            "initials": nombre[:2].upper(),
            "nombre":   nombre,
            "hora":     r.hora,
            "personas": r.comensales,
            "estado":   getattr(r, "estado", "Confirmada"),
        })
 
    # ── Stats ────────────────────────────────────────────────────────────
    total_hoy = len(reservas_hoy)
 
    # Reservas de ayer para el delta
    ayer_str = (hoy.replace(day=hoy.day - 1)).isoformat()
    total_ayer = db.session.query(Reserva).filter_by(
        restaurant_id=restaurant_record.id_restaurant
    ).filter(Reserva.fecha == ayer_str).count()
 
    delta = total_hoy - total_ayer
    delta_str = f"+{delta}" if delta >= 0 else str(delta)
 
    stats = {
        "reservas_hoy":    total_hoy,
        "reservas_delta":  delta_str,
        "ocupacion":       78,      # calculá con mesas disponibles / ocupadas
        "ocupacion_delta": "+5%",   # comparado semana anterior
        "platos_vistos":   245,     # desde analytics de menú si tenés
        "rating":          float(restaurant_record.puntaje or 0),
    }
 
    # ── Ocupación semanal ────────────────────────────────────────────────
    # Construí con reservas reales por día de la semana
    # Por ahora datos mock — reemplazá con queries reales
    ocupacion_semanal = [
        {"dia": "Lun", "pct": 65,  "hoy": hoy.weekday() == 0},
        {"dia": "Mar", "pct": 58,  "hoy": hoy.weekday() == 1},
        {"dia": "Mié", "pct": 72,  "hoy": hoy.weekday() == 2},
        {"dia": "Jue", "pct": 85,  "hoy": hoy.weekday() == 3},
        {"dia": "Vie", "pct": 92,  "hoy": hoy.weekday() == 4},
        {"dia": "Sáb", "pct": 78,  "hoy": hoy.weekday() == 5},
        {"dia": "Dom", "pct": 40,  "hoy": hoy.weekday() == 6},
    ]
 
    # ── Alerta dinámica (opcional) ───────────────────────────────────────
    alert = None
    if stats["ocupacion"] < 50:
        alert = {
            "title":        "Baja ocupación detectada — activá una oferta dinámica",
            "message":      "Tenés mesas disponibles en las próximas horas.",
            "action_label": "Activar oferta",
            "action_url":   url_for("restaurant.ofertas"),
        }
 
    return render_template(
        "restaurant_dashboard.html",
        restaurant=restaurant_data,
        today_label=today_label,
        stats=stats,
        reservas_hoy=reservas_hoy,
        ocupacion_semanal=ocupacion_semanal,
        alert=alert,
        active_page="dashboard",
    )