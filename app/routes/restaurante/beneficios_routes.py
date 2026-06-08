"""CRUD de Beneficios de fidelidad (lado socio)."""

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.database import db
from app.helpers.validators import (
    ValidationError,
    validate_choice,
    validate_decimal,
    validate_int,
    validate_text,
)
from app.models.beneficio import Beneficio
from app.models.enums import BeneficioValorTipo, CondicionTipo
from app.routes.restaurante import restaurante_bp
from app.routes.restaurante.dashboard import _admin_required, _get_owned_restaurant

_TIPO_LABELS = {
    BeneficioValorTipo.PORCENTAJE: "Porcentaje (%)",
    BeneficioValorTipo.MONTO_FIJO: "Monto fijo ($)",
}


def _get_owned_beneficio(restaurant, beneficio_id):
    return (
        db.session.query(Beneficio)
        .filter(
            Beneficio.id == beneficio_id,
            Beneficio.id_restaurante == restaurant.id_restaurant,
        )
        .first()
    )


def _beneficio_view(beneficio):
    return {
        "id": str(beneficio.id),
        "descripcion": beneficio.descripcion,
        "valor_condicion": beneficio.valor_condicion,
        "tipo_beneficio": beneficio.tipo_beneficio.value,
        "tipo_beneficio_label": _TIPO_LABELS.get(beneficio.tipo_beneficio, beneficio.tipo_beneficio.value),
        "valor_beneficio": f"{beneficio.valor_beneficio:g}",
        "activo": beneficio.activo,
    }


def _parse_beneficio_form(form):
    """Valida el formulario y devuelve los campos limpios. Lanza ValidationError."""
    descripcion = validate_text(
        form.get("descripcion", ""), "La descripción", min_length=3, max_length=200
    )
    valor_condicion = validate_int(
        form.get("valor_condicion", ""), "La cantidad de visitas", min_value=1, max_value=1000
    )
    tipo_raw = validate_choice(
        form.get("tipo_beneficio", ""),
        "El tipo de beneficio",
        {t.value for t in BeneficioValorTipo},
    )
    tipo_beneficio = BeneficioValorTipo(tipo_raw)
    valor_beneficio = validate_decimal(
        form.get("valor_beneficio", ""), "El valor del beneficio", min_value=1
    )
    if tipo_beneficio == BeneficioValorTipo.PORCENTAJE and valor_beneficio > 100:
        raise ValidationError("El porcentaje no puede superar el 100%.")
    return descripcion, valor_condicion, tipo_beneficio, valor_beneficio


@restaurante_bp.route("/restaurante/beneficios", methods=["GET", "POST"])
@login_required
def benefits():
    if not _admin_required():
        return redirect(url_for("usuario.home"))

    restaurant = _get_owned_restaurant()
    if restaurant is None:
        return redirect(url_for("restaurante.dashboard"))

    if request.method == "POST":
        try:
            descripcion, valor_condicion, tipo_beneficio, valor_beneficio = _parse_beneficio_form(request.form)
        except ValidationError as ex:
            flash(str(ex), "warning")
            return redirect(url_for("restaurante.benefits", open_drawer=1))

        beneficio = Beneficio(
            id_restaurante=restaurant.id_restaurant,
            descripcion=descripcion,
            tipo_condicion=CondicionTipo.VISITAS,
            valor_condicion=valor_condicion,
            tipo_beneficio=tipo_beneficio,
            valor_beneficio=valor_beneficio,
            activo=True,
        )
        db.session.add(beneficio)
        db.session.commit()
        flash("Beneficio creado correctamente.", "success")
        return redirect(url_for("restaurante.benefits"))

    beneficios = (
        db.session.query(Beneficio)
        .filter(Beneficio.id_restaurante == restaurant.id_restaurant)
        .order_by(Beneficio.created_at.desc())
        .all()
    )
    beneficios_view = [_beneficio_view(b) for b in beneficios]

    return render_template(
        "restaurante/beneficios.html",
        beneficios=beneficios_view,
        activos_count=sum(1 for b in beneficios_view if b["activo"]),
        tipo_options=[(t.value, _TIPO_LABELS[t]) for t in BeneficioValorTipo],
        active_admin_section="Beneficios",
        open_drawer=request.args.get("open_drawer") == "1",
    )


@restaurante_bp.route("/restaurante/beneficios/<uuid:beneficio_id>/edit", methods=["POST"])
@login_required
def edit_benefit(beneficio_id):
    if not _admin_required():
        return redirect(url_for("usuario.home"))

    restaurant = _get_owned_restaurant()
    if restaurant is None:
        return redirect(url_for("restaurante.dashboard"))

    beneficio = _get_owned_beneficio(restaurant, beneficio_id)
    if beneficio is None:
        flash("No se encontró el beneficio a editar.", "danger")
        return redirect(url_for("restaurante.benefits"))

    try:
        descripcion, valor_condicion, tipo_beneficio, valor_beneficio = _parse_beneficio_form(request.form)
    except ValidationError as ex:
        flash(str(ex), "warning")
        return redirect(url_for("restaurante.benefits"))

    beneficio.descripcion = descripcion
    beneficio.valor_condicion = valor_condicion
    beneficio.tipo_beneficio = tipo_beneficio
    beneficio.valor_beneficio = valor_beneficio
    db.session.commit()
    flash("Beneficio actualizado.", "success")
    return redirect(url_for("restaurante.benefits"))


@restaurante_bp.route("/restaurante/beneficios/<uuid:beneficio_id>/toggle", methods=["POST"])
@login_required
def toggle_benefit(beneficio_id):
    if not _admin_required():
        return redirect(url_for("usuario.home"))

    restaurant = _get_owned_restaurant()
    if restaurant is None:
        return redirect(url_for("restaurante.dashboard"))

    beneficio = _get_owned_beneficio(restaurant, beneficio_id)
    if beneficio is None:
        flash("No se encontró el beneficio.", "danger")
        return redirect(url_for("restaurante.benefits"))

    beneficio.activo = not beneficio.activo
    db.session.commit()
    flash("Beneficio " + ("activado." if beneficio.activo else "desactivado."), "success")
    return redirect(url_for("restaurante.benefits"))


@restaurante_bp.route("/restaurante/beneficios/<uuid:beneficio_id>/delete", methods=["POST"])
@login_required
def delete_benefit(beneficio_id):
    if not _admin_required():
        return redirect(url_for("usuario.home"))

    restaurant = _get_owned_restaurant()
    if restaurant is None:
        return redirect(url_for("restaurante.dashboard"))

    beneficio = _get_owned_beneficio(restaurant, beneficio_id)
    if beneficio is None:
        flash("No se encontró el beneficio a eliminar.", "danger")
        return redirect(url_for("restaurante.benefits"))

    db.session.delete(beneficio)
    db.session.commit()
    flash("Beneficio eliminado.", "success")
    return redirect(url_for("restaurante.benefits"))
