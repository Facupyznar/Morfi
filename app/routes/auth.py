from datetime import datetime
from urllib.parse import urlsplit

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.routing import BuildError

from app.database import db
from app.models.modelUser import ModelUser
from app.models.user import Role

auth_bp = Blueprint("auth", __name__)


def _resolve_next_url():
    next_url = request.args.get("next", "").strip()
    if next_url:
        parsed = urlsplit(next_url)
        if not parsed.scheme and not parsed.netloc:
            return next_url
    try:
        return url_for("home.index")
    except BuildError:
        return url_for("auth.home")


@auth_bp.route("/")
def home():
    if current_user.is_authenticated:
        return redirect(_resolve_next_url())
    return redirect(url_for("auth.login"))


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
            return render_template("login.html")

        user = ModelUser.login(db, username, password)
        if user:
            login_user(user, remember=remember)
            return redirect(_resolve_next_url())

        flash("Usuario o contraseña incorrectos.", "danger")

    return render_template("login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
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
            return render_template("register.html")

        if password != confirm_password:
            flash("Las contraseñas no coinciden.", "danger")
            return render_template("register.html")

        if birth_date_raw:
            try:
                birth_date = datetime.strptime(birth_date_raw, "%Y-%m-%d").date()
            except ValueError:
                flash("La fecha de nacimiento no tiene un formato válido.", "danger")
                return render_template("register.html")

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
            return render_template("register.html")
        except Exception:
            flash("No se pudo completar el registro.", "danger")
            return render_template("register.html")

        flash("¡Cuenta creada! Ya podés iniciar sesión.", "success")
        return redirect(url_for("auth.login"))

    return render_template("register.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Sesión cerrada correctamente.", "info")
    return redirect(url_for("auth.login"))
