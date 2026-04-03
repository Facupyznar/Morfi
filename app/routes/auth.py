from datetime import datetime
import re
from urllib.parse import urlsplit

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func
from werkzeug.routing import BuildError

from app.database import db
from app.models.modelUser import ModelUser
from app.models.user import Role, User

auth_bp = Blueprint("auth", __name__)


def _resolve_next_url():
    next_url = request.args.get("next", "").strip()
    if next_url:
        parsed = urlsplit(next_url)
        if not parsed.scheme and not parsed.netloc:
            return next_url
    try:
        return url_for("home.home")
    except BuildError:
        return url_for("auth.index")


def _resolve_register_role():
    raw_role = (request.form.get("role") or request.args.get("role") or Role.COMENSAL.value).strip()
    try:
        role = Role(raw_role)
    except ValueError:
        role = Role.COMENSAL

    allowed_roles = {Role.COMENSAL, Role.SOCIO_RESTAURANTE}
    if role not in allowed_roles:
        return Role.COMENSAL
    return role


def _build_partner_username(restaurant_name, email):
    base_value = (restaurant_name or email or "restaurante").strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", base_value).strip("_")[:40] or "restaurante"
    candidate = normalized
    suffix = 1

    while (
        db.session.query(User)
        .filter(func.lower(User.username) == candidate.lower())
        .first()
        is not None
    ):
        suffix += 1
        candidate = f"{normalized[:35]}_{suffix}"

    return candidate


@auth_bp.route('/')
def index():
    return render_template("auth/index.html")


@auth_bp.route('/register/selection')
def register_selection():
    return render_template('auth/selection.html')




@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(_resolve_next_url())

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        remember = request.form.get("remember") == "on"

        if not username or not password:
            flash("Usuario y contraseña son obligatorios.", "warning")
            return render_template("auth/login.html")

        user = ModelUser.login(db, username, password)
        if user:
            login_user(user, remember=remember)
            return redirect(_resolve_next_url())

        flash("Usuario o contraseña incorrectos.", "danger")

    return render_template("auth/login.html")


@auth_bp.route("/register")
def register():
    selected_role = _resolve_register_role()
    if selected_role == Role.SOCIO_RESTAURANTE:
        return redirect(url_for("auth.register_partner"))
    return redirect(url_for("auth.register_comensal"))


@auth_bp.route("/register/comensal", methods=["GET", "POST"])
def register_comensal():
    if current_user.is_authenticated:
        return redirect(_resolve_next_url())

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        name = request.form.get("name", "").strip()
        birth_date_raw = request.form.get("fecha", "").strip()
        birth_date = None

        if not username or not email or not password or not confirm_password:
            flash("Todos los campos marcados con * son obligatorios.", "warning")
            return render_template("auth/register.html")

        if password != confirm_password:
            flash("Las contraseñas no coinciden.", "danger")
            return render_template("auth/register.html")

        if birth_date_raw:
            try:
                birth_date = datetime.strptime(birth_date_raw, "%Y-%m-%d").date()
            except ValueError:
                flash("La fecha de nacimiento no tiene un formato válido.", "danger")
                return render_template("auth/register.html")

        try:
            ModelUser.register(
                db=db,
                username=username,
                email=email,
                password=password,
                name=name,
                birth_date=birth_date,
                rol=Role.COMENSAL,
            )
        except ValueError as ex:
            flash(str(ex), "danger")
            return render_template("auth/register.html")
        except Exception:
            flash("No se pudo completar el registro.", "danger")
            return render_template("auth/register.html")

        flash("¡Cuenta creada! Ya podés iniciar sesión.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html")


@auth_bp.route("/register/restaurante", methods=["GET", "POST"])
def register_partner():
    if current_user.is_authenticated:
        return redirect(_resolve_next_url())

    if request.method == "POST":
        restaurant_name = request.form.get("restaurant_name", "").strip()
        address = request.form.get("address", "").strip()
        contact_email = request.form.get("contact_email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not restaurant_name or not address or not contact_email or not password or not confirm_password:
            flash("Todos los campos obligatorios del restaurante deben completarse.", "warning")
            return render_template("auth/register_partner.html")

        if password != confirm_password:
            flash("Las contraseñas no coinciden.", "danger")
            return render_template("auth/register_partner.html")

        generated_username = _build_partner_username(restaurant_name, contact_email)

        try:
            ModelUser.register(
                db=db,
                username=generated_username,
                email=contact_email,
                password=password,
                name=restaurant_name,
                rol=Role.SOCIO_RESTAURANTE,
            )
        except ValueError as ex:
            flash(str(ex), "danger")
            return render_template("auth/register_partner.html")
        except Exception:
            flash("No se pudo completar el registro del restaurante.", "danger")
            return render_template("auth/register_partner.html")

        flash("Tu cuenta como socio restaurante fue creada y quedó enviada para verificación.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register_partner.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Sesión cerrada correctamente.", "info")
    return redirect(url_for("auth.login"))

@auth_bp.route("/login/restaurante", methods=["GET", "POST"])
def login_restaurante():
    if current_user.is_authenticated:
        return redirect(_resolve_next_url())
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = ModelUser.login(db, username, password)
        if user:
            login_user(user)
            return redirect(_resolve_next_url())
        flash("Usuario o contraseña incorrectos.", "danger")
    return render_template("auth/login_restaurante.html")