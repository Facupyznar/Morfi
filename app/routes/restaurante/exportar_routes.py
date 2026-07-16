"""Exportación de reportes PDF para el socio administrador."""

import io
from datetime import datetime, date, timedelta

from flask import make_response, redirect, render_template, request, url_for, flash
from flask_login import login_required

from app.database import db
from app.models.reserva import Reserva
from app.models.review import Review
from app.models.enums import ReservaStatus
from app.routes.restaurante import restaurante_bp
from app.routes.restaurante.dashboard import _admin_required, _get_owned_restaurant

try:
    from fpdf import FPDF
    FPDF_AVAILABLE = True
except ImportError:
    FPDF_AVAILABLE = False


# ── Helpers de datos ──────────────────────────────────────────────

def _parse_date(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw.strip())
    except (ValueError, AttributeError):
        return None


def _semanas(fecha_inicio: date, fecha_fin: date) -> list[dict]:
    """Divide el rango en bloques de 7 días y retorna info por semana."""
    semanas = []
    cur = fecha_inicio
    n = 1
    while cur <= fecha_fin:
        fin_semana = min(cur + timedelta(days=6), fecha_fin)
        semanas.append({"n": n, "inicio": cur, "fin": fin_semana})
        cur = fin_semana + timedelta(days=1)
        n += 1
    return semanas


def _datos_reservas(restaurant_id, fecha_inicio: date, fecha_fin: date) -> list[dict]:
    from sqlalchemy import cast, Date

    reservas = (
        db.session.query(Reserva)
        .filter(
            Reserva.id_restaurant == restaurant_id,
            cast(Reserva.fecha_hora, Date) >= fecha_inicio,
            cast(Reserva.fecha_hora, Date) <= fecha_fin,
        )
        .all()
    )

    semanas = _semanas(fecha_inicio, fecha_fin)
    rows = []
    for sem in semanas:
        en_semana = [
            r for r in reservas
            if sem["inicio"] <= r.fecha_hora.astimezone().date() <= sem["fin"]
        ]
        confirmadas   = [r for r in en_semana if r.estado_reserva in (ReservaStatus.CONFIRMADA, ReservaStatus.COMPLETADA)]
        canceladas    = [r for r in en_semana if r.estado_reserva == ReservaStatus.CANCELADA]
        comensales    = sum(r.cant_personas for r in confirmadas)
        rows.append({
            "label":      f"Semana {sem['n']}",
            "cantidad":   len(confirmadas),
            "comensales": comensales,
            "canceladas": len(canceladas),
        })
    total_res = sum(r["cantidad"] for r in rows)
    total_com = sum(r["comensales"] for r in rows)
    total_can = sum(r["canceladas"] for r in rows)
    return rows, total_res, total_com, total_can


def _datos_resenas(restaurant_id, fecha_inicio: date, fecha_fin: date):
    from sqlalchemy import func, cast, Date

    result = (
        db.session.query(func.avg(Review.puntaje), func.count(Review.id_review))
        .join(Reserva, Review.id_reserva == Reserva.id_reserva)
        .filter(
            Reserva.id_restaurant == restaurant_id,
            cast(Reserva.fecha_hora, Date) >= fecha_inicio,
            cast(Reserva.fecha_hora, Date) <= fecha_fin,
        )
        .one()
    )
    promedio, cantidad = result
    return round(float(promedio), 1) if promedio else 0.0, cantidad or 0


def _datos_ocupacion(restaurant, fecha_inicio: date, fecha_fin: date) -> list[dict]:
    from sqlalchemy import cast, Date
    semanas = _semanas(fecha_inicio, fecha_fin)
    capacidad = restaurant.capacidad or 0
    rows = []
    for sem in semanas:
        comensales = (
            db.session.query(db.func.coalesce(db.func.sum(Reserva.cant_personas), 0))
            .filter(
                Reserva.id_restaurant == restaurant.id_restaurant,
                Reserva.estado_reserva.in_([ReservaStatus.CONFIRMADA, ReservaStatus.COMPLETADA]),
                cast(Reserva.fecha_hora, Date) >= sem["inicio"],
                cast(Reserva.fecha_hora, Date) <= sem["fin"],
            )
            .scalar()
        )
        dias = (sem["fin"] - sem["inicio"]).days + 1
        cap_total = capacidad * dias
        pct = round(int(comensales) / cap_total * 100) if cap_total > 0 else 0
        rows.append({
            "label":      f"Semana {sem['n']}",
            "comensales": int(comensales),
            "capacidad":  cap_total,
            "pct":        pct,
        })
    return rows


# ── Generación PDF ────────────────────────────────────────────────

ORANGE = (193, 99, 26)
DARK   = (61, 53, 48)
GRAY   = (140, 133, 147)
LIGHT  = (245, 240, 235)
WHITE  = (255, 255, 255)


def _generar_pdf(restaurant, fecha_inicio, fecha_fin,
                 incluir_reservas, incluir_resenas, incluir_ocupacion) -> bytes:

    class PDF(FPDF):
        def header(self):
            # Banda naranja superior
            self.set_fill_color(*ORANGE)
            self.rect(0, 0, 210, 18, "F")
            self.set_font("Helvetica", "B", 14)
            self.set_text_color(*WHITE)
            self.set_xy(10, 4)
            self.cell(80, 10, "Morfi", ln=0)
            self.set_font("Helvetica", "", 8)
            label = f"REPORTE  {fecha_inicio.strftime('%Y-%m-%d')}  ->  {fecha_fin.strftime('%Y-%m-%d')}"
            self.set_x(210 - self.get_string_width(label) - 10)
            self.cell(0, 10, label, ln=0)
            self.ln(20)

        def footer(self):
            self.set_y(-12)
            self.set_font("Helvetica", "", 7)
            self.set_text_color(*GRAY)
            self.cell(0, 6, f"Generado el {date.today().strftime('%d/%m/%Y')}  ·  Página {self.page_no()}", align="C")

    pdf = PDF()
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()

    # ── Encabezado restaurante ────────────────────────────────────
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*DARK)
    pdf.cell(0, 8, restaurant.name, ln=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*GRAY)
    pdf.cell(0, 5, f"{restaurant.address}  ·  Reporte generado el {date.today().strftime('%d/%m/%Y')}", ln=True)
    pdf.ln(6)

    def section_title(title: str):
        pdf.set_fill_color(*LIGHT)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*ORANGE)
        pdf.cell(0, 8, f"  {title}", ln=True, fill=True)
        pdf.ln(3)

    def table_header(cols: list[tuple[str, int]]):
        pdf.set_fill_color(*DARK)
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*WHITE)
        for label, w in cols:
            pdf.cell(w, 7, label, border=0, fill=True, align="C")
        pdf.ln()

    def table_row(vals: list[tuple[str, int]], fill=False):
        pdf.set_fill_color(250, 247, 244) if fill else pdf.set_fill_color(*WHITE)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*DARK)
        for val, w in vals:
            pdf.cell(w, 6, str(val), border=0, fill=True, align="C")
        pdf.ln()

    # ── Sección Reservas ──────────────────────────────────────────
    if incluir_reservas:
        section_title("Reservas")
        rows, tot_res, tot_com, tot_can = _datos_reservas(
            restaurant.id_restaurant, fecha_inicio, fecha_fin)

        cols = [("Período", 50), ("Cantidad", 40), ("Comensales", 50), ("Cancelaciones", 50)]
        table_header(cols)
        for i, r in enumerate(rows):
            table_row([
                (r["label"], 50), (r["cantidad"], 40),
                (r["comensales"], 50), (r["canceladas"], 50),
            ], fill=i % 2 == 0)

        # Totales
        pdf.set_fill_color(*LIGHT)
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*DARK)
        for val, w in [("TOTAL", 50), (tot_res, 40), (tot_com, 50), (tot_can, 50)]:
            pdf.cell(w, 7, str(val), border=0, fill=True, align="C")
        pdf.ln(10)

    # ── Sección Reseñas ───────────────────────────────────────────
    if incluir_resenas:
        section_title("Reseñas")
        promedio, cantidad = _datos_resenas(restaurant.id_restaurant, fecha_inicio, fecha_fin)

        cols_r = [("Total reseñas", 95), ("Puntaje promedio", 95)]
        table_header(cols_r)
        table_row([(cantidad, 95), (f"{promedio} / 5", 95)], fill=True)
        pdf.ln(10)

    # ── Sección Ocupación ─────────────────────────────────────────
    if incluir_ocupacion:
        section_title("Ocupación semanal")
        rows_oc = _datos_ocupacion(restaurant, fecha_inicio, fecha_fin)

        cols_o = [("Período", 50), ("Comensales", 45), ("Cap. total", 45), ("Ocupación %", 50)]
        table_header(cols_o)
        max_pct = max((r["pct"] for r in rows_oc), default=1) or 1
        for i, r in enumerate(rows_oc):
            table_row([
                (r["label"], 50), (r["comensales"], 45),
                (r["capacidad"], 45), (f"{r['pct']}%", 50),
            ], fill=i % 2 == 0)

            # Mini barra de progreso
            bar_x = pdf.get_x() + 2
            bar_y = pdf.get_y() - 1
            bar_w = max(1, int(r["pct"] / max_pct * 60))
            pdf.set_fill_color(*ORANGE)
            pdf.rect(12, bar_y, bar_w, 2, "F")
            pdf.ln(2)
        pdf.ln(6)

    return bytes(pdf.output())


# ── Vistas ────────────────────────────────────────────────────────

@restaurante_bp.route("/restaurante/exportar", methods=["GET", "POST"])
@login_required
def exportar():
    if not _admin_required():
        return redirect(url_for("usuario.home"))

    restaurant = _get_owned_restaurant()
    if restaurant is None:
        return redirect(url_for("restaurante.dashboard"))

    if request.method == "GET":
        today = date.today()
        default_inicio = date(today.year, today.month, 1).isoformat()
        default_fin    = today.isoformat()
        return render_template(
            "restaurante/exportar.html",
            restaurant=restaurant,
            default_inicio=default_inicio,
            default_fin=default_fin,
            fpdf_available=FPDF_AVAILABLE,
            active_admin_section="Exportar",
            now=date.today().strftime("%d/%m/%Y"),
        )

    # POST: generar PDF
    if not FPDF_AVAILABLE:
        flash("La librería fpdf2 no está instalada. Ejecutá: pip install fpdf2", "danger")
        return redirect(url_for("restaurante.exportar"))

    fecha_inicio = _parse_date(request.form.get("fecha_inicio", ""))
    fecha_fin    = _parse_date(request.form.get("fecha_fin", ""))

    # DEBUG — borrar después
    from sqlalchemy import cast, Date as SADate
    print(f"DEBUG restaurant_id={restaurant.id_restaurant if restaurant else None}")
    print(f"DEBUG fecha_inicio={fecha_inicio} fecha_fin={fecha_fin}")
    if restaurant and fecha_inicio and fecha_fin:
        count = db.session.query(Reserva).filter(
            Reserva.id_restaurant == restaurant.id_restaurant,
            cast(Reserva.fecha_hora, SADate) >= fecha_inicio,
            cast(Reserva.fecha_hora, SADate) <= fecha_fin,
        ).count()
        print(f"DEBUG reservas en rango={count}")
    # FIN DEBUG

    if not fecha_inicio or not fecha_fin:
        flash("Fechas inválidas.", "warning")
        return redirect(url_for("restaurante.exportar"))
    if fecha_fin < fecha_inicio:
        flash("La fecha de fin debe ser posterior a la de inicio.", "warning")
        return redirect(url_for("restaurante.exportar"))

    incluir_reservas  = "reservas"  in request.form
    incluir_resenas   = "resenas"   in request.form
    incluir_ocupacion = "ocupacion" in request.form

    if not any([incluir_reservas, incluir_resenas, incluir_ocupacion]):
        flash("Seleccioná al menos una métrica.", "warning")
        return redirect(url_for("restaurante.exportar"))

    try:
        pdf_bytes = _generar_pdf(
            restaurant, fecha_inicio, fecha_fin,
            incluir_reservas, incluir_resenas, incluir_ocupacion,
        )
    except Exception as e:
        flash(f"Error generando el PDF: {e}", "danger")
        return redirect(url_for("restaurante.exportar"))

    nombre = f"reporte_{restaurant.name.replace(' ', '_')}_{fecha_inicio}_{fecha_fin}.pdf"
    response = make_response(pdf_bytes)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f"attachment; filename={nombre}"
    return response