from flask import abort, current_app, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.database import db
from app.helpers.security import csrf
from app.models.pago import Pago
from app.models.reserva import Reserva
from app.routes.usuario import usuario_bp

SENA_POR_PERSONA = 500


def _mp_enabled():
    return bool(current_app.config.get("MP_ENABLED"))


def _sdk():
    import mercadopago
    return mercadopago.SDK(current_app.config["MERCADOPAGO_ACCESS_TOKEN"])


def _monto_reserva(reserva):
    return round((reserva.cant_personas or 1) * SENA_POR_PERSONA, 2)


def _crear_preferencia(reserva, monto):
    restaurante = reserva.restaurant.name if reserva.restaurant else "tu reserva"
    retorno = url_for("usuario.pago_retorno", _external=True)
    data = {
        "items": [
            {
                "title": f"Seña reserva · {restaurante}",
                "quantity": 1,
                "currency_id": "ARS",
                "unit_price": float(monto),
            }
        ],
        "external_reference": str(reserva.id_reserva),
        "back_urls": {
            "success": retorno,
            "pending": retorno,
            "failure": retorno,
        },
        "notification_url": url_for("usuario.pago_webhook", _external=True),
    }
    if "localhost" not in retorno and "127.0.0.1" not in retorno:
        data["auto_return"] = "approved"
    result = _sdk().preference().create(data)
    return result.get("response", {})


def _procesar_payment(payment_id):
    try:
        result = _sdk().payment().get(payment_id)
    except Exception:
        return None
    payment = result.get("response", {}) or {}
    reserva_id = payment.get("external_reference")
    if not reserva_id:
        return None

    pago = (
        db.session.query(Pago)
        .filter_by(id_reserva=reserva_id)
        .order_by(Pago.created_at.desc())
        .first()
    )
    if pago is None:
        return None

    estado = payment.get("status") or "pendiente"
    ya_aprobado = pago.estado == "aprobado"
    pago.payment_id = str(payment_id)
    pago.estado = estado
    db.session.commit()

    if estado == "aprobado" and not ya_aprobado:
        try:
            from app.routes.usuario.notifications import crear_notificacion
            reserva = pago.reserva
            nombre = reserva.restaurant.name if reserva and reserva.restaurant else "tu reserva"
            crear_notificacion(
                user_id=reserva.user_id,
                tipo="reserva",
                titulo="Pago aprobado",
                descripcion=f"Confirmamos el pago de la seña · {nombre}",
                url_destino=url_for("usuario.history"),
            )
        except Exception:
            pass

    return pago


@usuario_bp.route("/reserva/<uuid:id_reserva>/pagar", methods=["POST"])
@login_required
def pagar_reserva(id_reserva):
    if not _mp_enabled():
        abort(404)

    reserva = Reserva.query.filter_by(
        id_reserva=id_reserva, user_id=current_user.user_id
    ).first_or_404()

    monto = _monto_reserva(reserva)
    pago = Pago(id_reserva=reserva.id_reserva, estado="pendiente", monto=monto)
    db.session.add(pago)
    db.session.commit()

    preferencia = _crear_preferencia(reserva, monto)
    print("MP PREFERENCIA RESPONSE:", preferencia, flush=True)
    pago.preference_id = preferencia.get("id")
    db.session.commit()

    destino = preferencia.get("sandbox_init_point") or preferencia.get("init_point")
    if not destino:
        return render_template("usuario/pago_resultado.html", estado="error")
    return redirect(destino)


@usuario_bp.route("/reserva/pago/retorno")
@login_required
def pago_retorno():
    if not _mp_enabled():
        abort(404)

    payment_id = request.args.get("payment_id") or request.args.get("collection_id")
    estado = request.args.get("status") or request.args.get("collection_status") or "pendiente"

    if payment_id:
        pago = _procesar_payment(payment_id)
        if pago is not None:
            estado = pago.estado

    return render_template("usuario/pago_resultado.html", estado=estado)


@usuario_bp.route("/mp/webhook", methods=["POST"])
@csrf.exempt
def pago_webhook():
    if not _mp_enabled():
        abort(404)

    payment_id = request.args.get("data.id") or request.args.get("id")
    if not payment_id:
        payload = request.get_json(silent=True) or {}
        payment_id = (payload.get("data") or {}).get("id") or payload.get("id")

    tipo = request.args.get("type") or (request.get_json(silent=True) or {}).get("type")
    if payment_id and (tipo in (None, "payment")):
        _procesar_payment(payment_id)

    return ("", 200)
