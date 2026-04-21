# ══════════════════════════════════════════════════════════════════
#  Rutas de Reservas — módulo restaurante
#  Pegar al final de app/routes/restaurante/dashboard.py
# ══════════════════════════════════════════════════════════════════
#
#  También agregar estos imports al tope de dashboard.py si no están:
#
#    from datetime import date, datetime, timedelta
#    from app.models.enums import ReservaStatus
#
# ══════════════════════════════════════════════════════════════════

import json
from datetime import date, datetime, timedelta, timezone

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.database import db
from app.models.enums import ReservaStatus
from app.models.reserva import Reserva
from app.models.restaurant import Restaurant
from app.models.user import Role
from app.routes.restaurante import restaurante_bp


# ── Helpers compartidos con dashboard.py ─────────────────────────

def _admin_required():
    role_value = getattr(getattr(current_user, "rol", None), "value", None)
    return role_value == Role.SOCIO_ADMIN.value


def _get_owned_restaurant():
    return (
        db.session.query(Restaurant)
        .filter(Restaurant.id_owner == current_user.user_id)
        .first()
    )


def _parse_horario(restaurant):
    if not restaurant.horario:
        return []
    try:
        data = json.loads(restaurant.horario)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


# ── Helpers ──────────────────────────────────────────────────────

AVATAR_COLORS = [
    "#2E4DB5", "#0B7A56", "#FF6B35", "#8B5CF6",
    "#D97706", "#0891B2", "#BE185D", "#065F46",
]

ALMUERZO_START = 12   # hora a partir de la cual es almuerzo
CENA_START     = 18   # hora a partir de la cual es cena


def _generar_slots(hora_apertura: str, hora_cierre: str, intervalo_min: int = 60):
    """
    Genera lista de strings 'HH:MM' cada `intervalo_min` minutos
    entre hora_apertura y hora_cierre (ambas 'HH:MM').
    """
    fmt = "%H:%M"
    try:
        inicio = datetime.strptime(hora_apertura, fmt)
        fin    = datetime.strptime(hora_cierre,   fmt)
    except ValueError:
        return []

    # Cierre de medianoche (00:00) → tratar como 23:30
    if fin <= inicio:
        fin = datetime.strptime("23:30", fmt)

    slots = []
    cur = inicio
    while cur <= fin:
        slots.append(cur.strftime(fmt))
        cur += timedelta(minutes=intervalo_min)  # intervalo = 60 min
    return slots


def _horario_del_dia(restaurant, dia_semana: int):
    """
    Devuelve (hora_apertura, hora_cierre) para el día dado (0=lunes…6=domingo).
    Las keys del JSON son: 'lun_jue', 'vie', 'sab', 'dom'.
    Retorna (None, None) si el restaurante está cerrado ese día.
    """
    horario = _parse_horario(restaurant)

    if dia_semana <= 3:
        key = "lun_jue"
    elif dia_semana == 4:
        key = "vie"
    elif dia_semana == 5:
        key = "sab"
    else:
        key = "dom"

    for entry in horario:
        if entry.get("key") == key and entry.get("active"):
            apertura = entry.get("open",  "12:00")
            cierre   = entry.get("close", "23:00")
            return apertura, cierre

    # Fallback si no tiene horario configurado
    if not horario:
        return "12:00", "23:00"
    return None, None


def _ocupados_en_slot(restaurant_id, fecha: date, hora_str: str) -> int:
    """Suma los comensales de reservas CONFIRMADAS para fecha+hora."""
    arg_tz = timezone(timedelta(hours=-3))
    hora = datetime.strptime(hora_str, "%H:%M").time()
    inicio_slot = datetime.combine(fecha, hora).replace(tzinfo=arg_tz).astimezone(timezone.utc)
    fin_slot    = inicio_slot + timedelta(minutes=60)

    from sqlalchemy import and_
    result = (
        db.session.query(db.func.coalesce(db.func.sum(Reserva.cant_personas), 0))
        .filter(
            Reserva.id_restaurant == restaurant_id,
            Reserva.estado_reserva == ReservaStatus.CONFIRMADA,
            Reserva.fecha_hora >= inicio_slot,
            Reserva.fecha_hora <  fin_slot,
        )
        .scalar()
    )
    return int(result or 0)


def _build_slots(restaurant, fecha: date):
    """
    Devuelve (slots_almuerzo, slots_cena) como listas de dicts:
    { hora, ocupados, disponibles, pct }
    """
    apertura, cierre = _horario_del_dia(restaurant, fecha.weekday())

    if not apertura:
        return [], []

    todas = _generar_slots(apertura, cierre)
    capacidad = restaurant.capacidad or 1

    almuerzo, cena = [], []
    for hora in todas:
        h = int(hora.split(":")[0])
        ocupados    = _ocupados_en_slot(restaurant.id_restaurant, fecha, hora)
        disponibles = max(capacidad - ocupados, 0)
        pct         = round((ocupados / capacidad) * 100)

        slot = {
            "hora":        hora,
            "ocupados":    ocupados,
            "disponibles": disponibles,
            "pct":         pct,
        }
        if h < CENA_START:
            almuerzo.append(slot)
        else:
            cena.append(slot)

    return almuerzo, cena


# ── Vista principal ───────────────────────────────────────────────

@restaurante_bp.route("/restaurante/reservas")
@login_required
def reservations():
    if not _admin_required():
        return redirect(url_for("usuario.home"))

    restaurant = _get_owned_restaurant()
    if restaurant is None:
        flash("No tenés un restaurante asociado.", "warning")
        return redirect(url_for("restaurante.dashboard"))

    # Fecha seleccionada (query param ?fecha=YYYY-MM-DD, default hoy)
    fecha_param = request.args.get("fecha")
    try:
        fecha = date.fromisoformat(fecha_param) if fecha_param else date.today()
    except ValueError:
        fecha = date.today()

    hoy    = date.today()
    es_hoy = fecha == hoy

    # Etiqueta legible de la fecha
    dias_es   = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    meses_es  = ["Enero","Febrero","Marzo","Abril","Mayo","Junio",
                 "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
    fecha_label = f"{dias_es[fecha.weekday()]} {fecha.day} de {meses_es[fecha.month - 1]}"

    fecha_anterior = (fecha - timedelta(days=1)).isoformat()
    fecha_siguiente = (fecha + timedelta(days=1)).isoformat()

    # Slots de capacidad
    slots_almuerzo, slots_cena = _build_slots(restaurant, fecha)

    # Reservas del día
    ARG_TZ = timezone(timedelta(hours=-3))
    inicio_dia = datetime(fecha.year, fecha.month, fecha.day, tzinfo=ARG_TZ)
    fin_dia    = inicio_dia + timedelta(days=1)

    reservas = (
        db.session.query(Reserva)
        .filter(
            Reserva.id_restaurant == restaurant.id_restaurant,
            Reserva.fecha_hora    >= inicio_dia,
            Reserva.fecha_hora    <  fin_dia,
        )
        .order_by(Reserva.fecha_hora)
        .all()
    )

    # Asignar color de avatar y hora local (Argentina) por reserva
    for i, r in enumerate(reservas):
        r.avatar_color = AVATAR_COLORS[i % len(AVATAR_COLORS)]
        fh = r.fecha_hora
        r.hora_local = (fh.astimezone(ARG_TZ) if fh.tzinfo else fh).strftime('%H:%M')

    # Stats del día
    confirmadas = sum(1 for r in reservas if r.estado_reserva == ReservaStatus.CONFIRMADA)
    pendientes  = sum(1 for r in reservas if r.estado_reserva == ReservaStatus.PENDIENTE)
    ocupacion   = sum(
        r.cant_personas for r in reservas
        if r.estado_reserva == ReservaStatus.CONFIRMADA
    )

    stats = {
        "confirmadas":   confirmadas,
        "pendientes":    pendientes,
        "ocupacion_hoy": ocupacion,
    }

    default_horario = [
        {'key':'lun_jue','label':'Lun – Jue','open':'12:00','close':'23:00','active':True},
        {'key':'vie',    'label':'Viernes',  'open':'12:00','close':'00:00','active':True},
        {'key':'sab',    'label':'Sábado',   'open':'11:00','close':'00:00','active':True},
        {'key':'dom',    'label':'Domingo',  'open':'11:00','close':'22:00','active':True},
    ]
    horario_config = _parse_horario(restaurant) or default_horario

    return render_template(
        "restaurante/reservas.html",
        restaurant      = restaurant,
        reservas        = reservas,
        stats           = stats,
        slots_almuerzo  = slots_almuerzo,
        slots_cena      = slots_cena,
        fecha_label     = fecha_label,
        fecha_anterior  = fecha_anterior,
        fecha_siguiente = fecha_siguiente,
        es_hoy          = es_hoy,
        slot_activo     = None,
        horario_config  = horario_config,
        active_admin_section = "Reservas",
    )


# ── Confirmar reserva ─────────────────────────────────────────────

@restaurante_bp.route("/restaurante/reservas/<uuid:id_reserva>/confirmar", methods=["POST"])
@login_required
def confirmar_reserva(id_reserva):
    if not _admin_required():
        return redirect(url_for("usuario.home"))

    restaurant = _get_owned_restaurant()
    reserva = Reserva.query.filter_by(
        id_reserva=id_reserva,
        id_restaurant=restaurant.id_restaurant
    ).first_or_404()

    reserva.estado_reserva = ReservaStatus.CONFIRMADA
    db.session.commit()
    flash("Reserva confirmada.", "success")

    fecha = reserva.fecha_hora.date().isoformat()
    return redirect(url_for("restaurante.reservations", fecha=fecha))


# ── Cancelar reserva ──────────────────────────────────────────────

@restaurante_bp.route("/restaurante/reservas/<uuid:id_reserva>/cancelar", methods=["POST"])
@login_required
def cancelar_reserva(id_reserva):
    if not _admin_required():
        return redirect(url_for("usuario.home"))

    restaurant = _get_owned_restaurant()
    reserva = Reserva.query.filter_by(
        id_reserva=id_reserva,
        id_restaurant=restaurant.id_restaurant
    ).first_or_404()

    reserva.estado_reserva = ReservaStatus.CANCELADA
    db.session.commit()
    flash("Reserva cancelada.", "info")

    fecha = reserva.fecha_hora.date().isoformat()
    return redirect(url_for("restaurante.reservations", fecha=fecha))


# ── Cambiar estado (AJAX) ─────────────────────────────────────────

@restaurante_bp.route("/restaurante/reservas/<uuid:id_reserva>/estado", methods=["POST"])
@login_required
def cambiar_estado_reserva(id_reserva):
    from flask import jsonify
    if not _admin_required():
        return jsonify({"error": "Sin permiso"}), 403

    restaurant = _get_owned_restaurant()
    reserva = Reserva.query.filter_by(
        id_reserva    = id_reserva,
        id_restaurant = restaurant.id_restaurant,
    ).first_or_404()

    estado_map = {
        "confirmada": ReservaStatus.CONFIRMADA,
        "pendiente":  ReservaStatus.PENDIENTE,
        "cancelada":  ReservaStatus.CANCELADA,
        "completada": ReservaStatus.COMPLETADA,
    }

    nuevo = request.form.get("estado", "").lower()
    if nuevo not in estado_map:
        return jsonify({"error": "Estado inválido"}), 400

    reserva.estado_reserva = estado_map[nuevo]
    db.session.commit()

    return jsonify({
        "ok":     True,
        "estado": nuevo,
    })


# ── Configuración: capacidad y horarios ──────────────────────────

@restaurante_bp.route("/restaurante/reservas/config", methods=["POST"])
@login_required
def reservas_config():
    if not _admin_required():
        return redirect(url_for("usuario.home"))

    restaurant = _get_owned_restaurant()
    if restaurant is None:
        return redirect(url_for("restaurante.dashboard"))

    # Capacidad
    capacidad_raw = (request.form.get("capacidad") or "").strip()
    if capacidad_raw.isdigit() and int(capacidad_raw) > 0:
        restaurant.capacidad = int(capacidad_raw)
    else:
        flash("La capacidad debe ser un número mayor a 0.", "warning")
        return redirect(url_for("restaurante.reservations"))

    # Horario (JSON enviado por el editor de franjas)
    import json as _json
    horario_raw = (request.form.get("horario") or "[]").strip()
    try:
        horario_data = _json.loads(horario_raw)
        if isinstance(horario_data, list):
            restaurant.horario = _json.dumps(horario_data, ensure_ascii=False)
    except (_json.JSONDecodeError, TypeError):
        flash("Error al guardar el horario.", "danger")
        return redirect(url_for("restaurante.reservations"))

    db.session.commit()
    flash("Configuración guardada correctamente.", "success")
    return redirect(url_for("restaurante.reservations"))
