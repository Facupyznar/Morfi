"""CRUD de Ofertas temporales (lado socio)."""

from datetime import datetime

from flask import flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.database import db
from app.helpers.validators import (
    ValidationError,
    validate_image_file,
    validate_text,
)
from app.models.oferta import Oferta
from app.routes.restaurante import restaurante_bp
from app.routes.restaurante.dashboard import (
    _admin_required,
    _get_owned_restaurant,
    _save_img,
)


def _get_owned_oferta(restaurant, oferta_id):
    return (
        db.session.query(Oferta)
        .filter(
            Oferta.id == oferta_id,
            Oferta.id_restaurante == restaurant.id_restaurant,
        )
        .first()
    )


def _parse_fecha(raw, field_label):
    if not raw or not raw.strip():
        raise ValidationError(f"{field_label} es obligatoria.")
    try:
        return datetime.fromisoformat(raw.strip())
    except ValueError:
        raise ValidationError(f"{field_label} no tiene un formato válido.")


def _parse_oferta_form(form, files, is_edit=False):
    """Valida el formulario de oferta. Lanza ValidationError. No guarda la imagen."""
    titulo = validate_text(form.get("titulo", ""), "El título", min_length=3, max_length=120)
    descripcion = validate_text(
        form.get("descripcion", ""), "La descripción", required=False, max_length=400
    ) or None
    fecha_inicio = _parse_fecha(form.get("fecha_inicio", ""), "La fecha de inicio")
    fecha_fin = _parse_fecha(form.get("fecha_fin", ""), "La fecha de fin")
    now = datetime.now()
    if not is_edit and fecha_inicio < now:
        raise ValidationError("La fecha de inicio no puede ser en el pasado.")
    if fecha_fin <= now:
        raise ValidationError("La fecha de fin no puede ser en el pasado.")
    if fecha_fin <= fecha_inicio:
        raise ValidationError("La fecha de fin debe ser posterior a la fecha de inicio.")
    validate_image_file(files.get("imagen"), field_label="La imagen de la oferta")
    return titulo, descripcion, fecha_inicio, fecha_fin


def _naive_dt(dt):
    """Quita tzinfo para comparar con datetime.now() (naive local)."""
    if dt is None:
        return None
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def _estado_oferta(oferta) -> str:
    """Devuelve 'vigente', 'proxima', 'vencida' o 'inactiva'."""
    if not oferta.activo:
        return "inactiva"
    now = datetime.now()
    inicio = _naive_dt(oferta.fecha_inicio)
    fin    = _naive_dt(oferta.fecha_fin)
    if fin and now > fin:
        return "vencida"
    if inicio and now < inicio:
        return "proxima"
    return "vigente"


def _oferta_view(oferta):
    estado = _estado_oferta(oferta)
    return {
        "id": str(oferta.id),
        "titulo": oferta.titulo,
        "descripcion": oferta.descripcion or "",
        "imagen_path": oferta.imagen_path,
        "fecha_inicio": oferta.fecha_inicio.strftime("%Y-%m-%dT%H:%M") if oferta.fecha_inicio else "",
        "fecha_fin": oferta.fecha_fin.strftime("%Y-%m-%dT%H:%M") if oferta.fecha_fin else "",
        "fecha_inicio_label": oferta.fecha_inicio.strftime("%d/%m/%Y %H:%M") if oferta.fecha_inicio else "",
        "fecha_fin_label": oferta.fecha_fin.strftime("%d/%m/%Y %H:%M") if oferta.fecha_fin else "",
        "activo": oferta.activo,
        "vigente": estado == "vigente",
        "estado": estado,
    }


def _es_vigente(oferta):
    return _estado_oferta(oferta) == "vigente"


@restaurante_bp.route("/restaurante/ofertas", methods=["GET", "POST"])
@login_required
def offers():
    if not _admin_required():
        return redirect(url_for("usuario.home"))

    restaurant = _get_owned_restaurant()
    if restaurant is None:
        return redirect(url_for("restaurante.dashboard"))

    if request.method == "POST":
        try:
            titulo, descripcion, fecha_inicio, fecha_fin = _parse_oferta_form(request.form, request.files)
        except ValidationError as ex:
            flash(str(ex), "warning")
            return redirect(url_for("restaurante.offers", open_drawer=1))

        imagen_path = None
        imagen_file = request.files.get("imagen")
        if imagen_file and imagen_file.filename:
            imagen_path = _save_img(imagen_file, "ofertas", str(restaurant.id_restaurant))

        oferta = Oferta(
            id_restaurante=restaurant.id_restaurant,
            titulo=titulo,
            descripcion=descripcion,
            imagen_path=imagen_path,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            activo=True,
        )
        db.session.add(oferta)
        db.session.commit()
        flash("Oferta creada correctamente.", "success")
        return redirect(url_for("restaurante.offers"))

    ofertas = (
        db.session.query(Oferta)
        .filter(Oferta.id_restaurante == restaurant.id_restaurant)
        .order_by(Oferta.fecha_fin.desc())
        .all()
    )
    ofertas_view = [_oferta_view(o) for o in ofertas]

    return render_template(
        "restaurante/ofertas.html",
        ofertas=ofertas_view,
        vigentes_count=sum(1 for o in ofertas_view if o["vigente"]),
        active_admin_section="Ofertas",
        open_drawer=request.args.get("open_drawer") == "1",
    )


@restaurante_bp.route("/restaurante/ofertas/<uuid:oferta_id>/edit", methods=["POST"])
@login_required
def edit_offer(oferta_id):
    if not _admin_required():
        return redirect(url_for("usuario.home"))

    restaurant = _get_owned_restaurant()
    if restaurant is None:
        return redirect(url_for("restaurante.dashboard"))

    oferta = _get_owned_oferta(restaurant, oferta_id)
    if oferta is None:
        flash("No se encontró la oferta a editar.", "danger")
        return redirect(url_for("restaurante.offers"))

    try:
        titulo, descripcion, fecha_inicio, fecha_fin = _parse_oferta_form(request.form, request.files)
    except ValidationError as ex:
        flash(str(ex), "warning")
        return redirect(url_for("restaurante.offers"))

    oferta.titulo = titulo
    oferta.descripcion = descripcion
    oferta.fecha_inicio = fecha_inicio
    oferta.fecha_fin = fecha_fin

    imagen_file = request.files.get("imagen")
    if imagen_file and imagen_file.filename:
        nuevo_path = _save_img(imagen_file, "ofertas", str(restaurant.id_restaurant))
        if nuevo_path:
            oferta.imagen_path = nuevo_path

    db.session.commit()
    flash("Oferta actualizada.", "success")
    return redirect(url_for("restaurante.offers"))


@restaurante_bp.route("/restaurante/ofertas/<uuid:oferta_id>/toggle", methods=["POST"])
@login_required
def toggle_offer(oferta_id):
    if not _admin_required():
        return redirect(url_for("usuario.home"))

    restaurant = _get_owned_restaurant()
    if restaurant is None:
        return redirect(url_for("restaurante.dashboard"))

    oferta = _get_owned_oferta(restaurant, oferta_id)
    if oferta is None:
        flash("No se encontró la oferta.", "danger")
        return redirect(url_for("restaurante.offers"))

    oferta.activo = not oferta.activo
    db.session.commit()
    flash("Oferta " + ("activada." if oferta.activo else "desactivada."), "success")
    return redirect(url_for("restaurante.offers"))


@restaurante_bp.route("/restaurante/ofertas/<uuid:oferta_id>/delete", methods=["POST"])
@login_required
def delete_offer(oferta_id):
    if not _admin_required():
        return redirect(url_for("usuario.home"))

    restaurant = _get_owned_restaurant()
    if restaurant is None:
        return redirect(url_for("restaurante.dashboard"))

    oferta = _get_owned_oferta(restaurant, oferta_id)
    if oferta is None:
        flash("No se encontró la oferta a eliminar.", "danger")
        return redirect(url_for("restaurante.offers"))

    db.session.delete(oferta)
    db.session.commit()
    flash("Oferta eliminada.", "success")
    return redirect(url_for("restaurante.offers"))