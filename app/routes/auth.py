from datetime import datetime
import os
import re
import uuid
from urllib.parse import urlsplit

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import and_, func, or_
from werkzeug.security import generate_password_hash
from werkzeug.routing import BuildError
from werkzeug.utils import secure_filename

from app.database import db
from app.helpers.oauth import oauth
from app.helpers.security import csrf
from app.helpers.validators import (
    ValidationError,
    validate_birth_date,
    validate_email,
    validate_file,
    validate_password,
    validate_password_confirmation,
    validate_tag_names,
    validate_text,
    validate_username,
)
from app.location import resolve_location_payload
from app.helpers.auth import ModelUser
from app.models.enums import TagCategory
from app.models.restaurant import Restaurant
from app.models.tag import Tag
from app.models.user import Role, User
from app.models.user_tags import UserTags

auth_bp = Blueprint("auth", __name__)

ALLOWED_ONBOARDING_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


@auth_bp.after_request
def add_no_store_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


def _resolve_next_url():
    next_url = request.args.get("next", "").strip()
    if next_url:
        parsed = urlsplit(next_url)
        if not parsed.scheme and not parsed.netloc:
            return next_url
    return _resolve_post_login_redirect(current_user)


def _resolve_post_login_redirect(user):
    role_value = getattr(user, "role", None)
    try:
        if role_value in {Role.COMENSAL.value, Role.ADMIN_GLOBAL.value}:
            return url_for("usuario.home")
        if role_value == Role.SOCIO_ADMIN.value:
            return url_for("restaurante.dashboard")
        return url_for("auth.index")
    except BuildError:
        return url_for("auth.index")


def _resolve_register_role():
    raw_role = (request.form.get("role") or request.args.get("role") or Role.COMENSAL.value).strip()
    try:
        role = Role(raw_role)
    except ValueError:
        role = Role.COMENSAL

    allowed_roles = {Role.COMENSAL, Role.SOCIO_ADMIN}
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


def _extract_form_values(field_names):
    return {field_name: request.form.get(field_name, "") for field_name in field_names}


@auth_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(_resolve_next_url())
    return render_template("auth/index.html")


@auth_bp.route('/register/selection')
def register_selection():
    if current_user.is_authenticated:
        return redirect(_resolve_next_url())
    return render_template('auth/selection.html')




@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(_resolve_next_url())

    if request.method == "POST":
        try:
            username = validate_username(request.form.get("username", ""))
            password = validate_password(
                request.form.get("password", ""),
                field_label="La contraseña",
            )
        except ValidationError as ex:
            flash(str(ex), "warning")
            return render_template("auth/login.html")
        remember = request.form.get("remember") == "on"

        user = ModelUser.login(db, username, password)
        if user:
            if not getattr(user, "is_active", True):
                flash("Tu cuenta está suspendida. Contactá al equipo de soporte.", "danger")
                return render_template("auth/login.html")
            if user.role not in {Role.COMENSAL.value, Role.ADMIN_GLOBAL.value}:
                flash("Esta cuenta no puede iniciar sesión desde el acceso de comensal.", "danger")
                return render_template("auth/login.html")
            login_user(user, remember=remember)
            return redirect(_resolve_post_login_redirect(user))

        flash("Usuario o contraseña incorrectos.", "danger")

    return render_template("auth/login.html")


@auth_bp.route("/register")
def register():
    if current_user.is_authenticated:
        return redirect(_resolve_next_url())
    selected_role = _resolve_register_role()
    if selected_role == Role.SOCIO_ADMIN:
        return redirect(url_for("auth.register_partner"))
    return redirect(url_for("auth.register_comensal"))


@auth_bp.route("/register/comensal", methods=["GET", "POST"])
def register_comensal():
    if current_user.is_authenticated:
        return redirect(_resolve_next_url())

    form_fields = [
        "name",
        "username",
        "email",
        "address",
        "latitude",
        "longitude",
        "fecha",
    ]
    form_data = _extract_form_values(form_fields)

    if request.method == "POST":
        try:
            username = validate_username(request.form.get("username", ""))
            email = validate_email(request.form.get("email", ""))
            password = validate_password(request.form.get("password", ""), field_label="La contraseña")
            confirm_password = request.form.get("confirm_password", "")
            validate_password_confirmation(password, confirm_password)
            name = validate_text(request.form.get("name", ""), "El nombre completo", min_length=2, max_length=50)
            address = validate_text(request.form.get("address", ""), "La dirección", min_length=3, max_length=255)
            birth_date = validate_birth_date(request.form.get("fecha", "").strip())
        except ValidationError as ex:
            flash(str(ex), "danger")
            return render_template("auth/register.html", form_data=form_data)

        latitude = request.form.get("latitude")
        longitude = request.form.get("longitude")

        try:
            location_payload = resolve_location_payload(address, latitude, longitude)
        except ValueError as ex:
            flash(str(ex), "danger")
            return render_template("auth/register.html", form_data=form_data)

        try:
            ModelUser.register(
                db=db,
                username=username,
                email=email,
                password=password,
                name=name,
                birth_date=birth_date,
                rol=Role.COMENSAL,
                address=location_payload["address"],
                latitude=location_payload["latitude"],
                longitude=location_payload["longitude"],
            )
        except ValueError as ex:
            flash(str(ex), "danger")
            return render_template("auth/register.html", form_data=form_data)
        except Exception:
            flash("No se pudo completar el registro.", "danger")
            return render_template("auth/register.html", form_data=form_data)

        flash("¡Cuenta creada! Ya podés iniciar sesión.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html", form_data=form_data)


@auth_bp.route("/register/restaurante", methods=["GET", "POST"])
@auth_bp.route("/register-partner", methods=["GET", "POST"])
def register_partner():
    if current_user.is_authenticated:
        return redirect(_resolve_next_url())

    form_fields = [
        "name",
        "username",
        "address",
        "latitude",
        "longitude",
        "email",
    ]
    form_data = _extract_form_values(form_fields)

    if request.method == "POST":
        latitude = request.form.get("latitude")
        longitude = request.form.get("longitude")
        legal_doc = request.files.get("doc_legal")
        try:
            name = validate_text(request.form.get("name", ""), "El nombre del restaurante", min_length=2, max_length=50)
            username = validate_username(request.form.get("username", ""))
            email = validate_email(request.form.get("email", ""), "El email de contacto")
            address = validate_text(request.form.get("address", ""), "La dirección", min_length=3, max_length=255)
            password = validate_password(request.form.get("password", ""), field_label="La contraseña")
            confirm_password = request.form.get("confirm_password", "")
            validate_password_confirmation(password, confirm_password)
            validate_file(
                legal_doc,
                field_label="La documentación legal",
                allowed_extensions={".pdf", ".jpg", ".jpeg", ".png"},
                max_size_mb=10,
            )
        except ValidationError as ex:
            flash(str(ex), "danger")
            return render_template("auth/register_partner.html", form_data=form_data)

        try:
            location_payload = resolve_location_payload(address, latitude, longitude)
        except ValueError as ex:
            flash(str(ex), "danger")
            return render_template("auth/register_partner.html", form_data=form_data)

        if db.session.query(User).filter(func.lower(User.username) == username.lower()).first():
            flash("El nombre de usuario ya está en uso.", "danger")
            return render_template("auth/register_partner.html", form_data=form_data)

        if db.session.query(User).filter(func.lower(User.email) == email.lower()).first():
            flash("El correo electrónico ya está registrado.", "danger")
            return render_template("auth/register_partner.html", form_data=form_data)

        try:
            user = User(
                username=username,
                email=email,
                password=password,
                name=name,
                rol=Role.SOCIO_ADMIN,
                address=location_payload["address"],
                latitude=location_payload["latitude"],
                longitude=location_payload["longitude"],
                is_admin=True,
            )
            user.password_hash = generate_password_hash(password, method="pbkdf2:sha256")
            db.session.add(user)
            db.session.flush()

            restaurant = Restaurant(
                id_owner=user.user_id,
                name=name,
                address=location_payload["address"],
                latitude=location_payload["latitude"],
                longitude=location_payload["longitude"],
            )
            db.session.add(restaurant)
            db.session.commit()
        except ValueError as ex:
            db.session.rollback()
            flash(str(ex), "danger")
            return render_template("auth/register_partner.html", form_data=form_data)
        except Exception:
            db.session.rollback()
            flash("No se pudo completar el registro del restaurante.", "danger")
            return render_template("auth/register_partner.html", form_data=form_data)

        login_user(user)
        flash("Tu cuenta y tu restaurante fueron creados correctamente.", "success")
        return redirect(_resolve_post_login_redirect(user))

    return render_template("auth/register_partner.html", form_data=form_data)


# ── Login con Google (OAuth / OpenID Connect) ─────────────────────

def _build_username_from_email(email):
    """Genera un username único a partir del email de Google."""
    local_part = (email or "").split("@")[0]
    normalized = re.sub(r"[^a-z0-9]+", "_", local_part.lower()).strip("_")[:40] or "comensal"
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


def _load_onboarding_tags():
    all_tags = db.session.query(Tag).order_by(Tag.name).all()
    cuisine_tags = [tag for tag in all_tags if tag.category == TagCategory.COMIDA]
    restriction_tags = [tag for tag in all_tags if tag.category == TagCategory.DIETA]
    return cuisine_tags, restriction_tags


def _selected_tag_names(user_record):
    cuisine_names, restriction_names = [], []
    for user_tag in getattr(user_record, "user_tags", []):
        if not user_tag.tag:
            continue
        if user_tag.tag.category == TagCategory.COMIDA:
            cuisine_names.append(user_tag.tag.name)
        elif user_tag.tag.category == TagCategory.DIETA:
            restriction_names.append(user_tag.tag.name)
    return cuisine_names, restriction_names


def _save_onboarding_photo(uploaded_file):
    filename = secure_filename(uploaded_file.filename or "")
    _, extension = os.path.splitext(filename.lower())
    if not extension or extension not in ALLOWED_ONBOARDING_IMAGE_EXTENSIONS:
        raise ValueError("La foto debe ser JPG, PNG, WEBP o GIF.")

    upload_dir = os.path.join(current_app.root_path, "static", "uploads", "profile")
    os.makedirs(upload_dir, exist_ok=True)

    generated_name = f"{uuid.uuid4().hex}{extension}"
    uploaded_file.save(os.path.join(upload_dir, generated_name))
    return f"uploads/profile/{generated_name}"


@auth_bp.route("/login/google")
@csrf.exempt
def login_google():
    if current_user.is_authenticated:
        return redirect(_resolve_next_url())

    google = oauth.create_client("google")
    if google is None:
        flash("El inicio de sesión con Google no está disponible en este momento.", "warning")
        return redirect(url_for("auth.login"))

    redirect_uri = current_app.config.get("GOOGLE_OAUTH_REDIRECT_URI") or url_for(
        "auth.google_callback", _external=True
    )
    return google.authorize_redirect(redirect_uri)


@auth_bp.route("/login/google/callback")
@csrf.exempt
def google_callback():
    google = oauth.create_client("google")
    if google is None:
        flash("El inicio de sesión con Google no está disponible en este momento.", "warning")
        return redirect(url_for("auth.login"))

    try:
        token = google.authorize_access_token()
    except Exception:
        flash("No pudimos validar tu inicio de sesión con Google.", "danger")
        return redirect(url_for("auth.login"))

    userinfo = token.get("userinfo") or {}
    google_sub = userinfo.get("sub")
    email = (userinfo.get("email") or "").strip().lower()
    email_verified = bool(userinfo.get("email_verified"))
    name = userinfo.get("name")
    picture = userinfo.get("picture")

    if not google_sub:
        flash("No pudimos obtener tu identidad de Google.", "danger")
        return redirect(url_for("auth.login"))

    # 1) Usuario ya vinculado por google_id.
    user = db.session.query(User).filter_by(google_id=google_sub).first()

    # 2) Vinculación por email SOLO si Google verificó el correo.
    if user is None and email and email_verified:
        existing = (
            db.session.query(User).filter(func.lower(User.email) == email).first()
        )
        if existing is not None:
            existing.google_id = google_sub
            if not existing.avatar_url and picture:
                existing.avatar_url = picture
            db.session.commit()
            user = existing

    # 3) Alta nueva como COMENSAL pendiente de onboarding.
    if user is None:
        if not email:
            flash("Tu cuenta de Google no tiene un email disponible.", "danger")
            return redirect(url_for("auth.login"))
        try:
            user = User(
                username=_build_username_from_email(email),
                email=email,
                name=name,
                rol=Role.COMENSAL,
                avatar_url=picture,
                profile_completed=False,
            )
            db.session.add(user)
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("No se pudo completar el alta con Google.", "danger")
            return redirect(url_for("auth.login"))

    if not getattr(user, "is_active", True):
        flash("Tu cuenta está suspendida. Contactá al equipo de soporte.", "danger")
        return redirect(url_for("auth.login"))

    login_user(user)

    if not user.profile_completed:
        return redirect(url_for("auth.onboarding"))
    return redirect(_resolve_post_login_redirect(user))


@auth_bp.route("/onboarding", methods=["GET", "POST"])
@login_required
def onboarding():
    user = current_user

    # Si ya completó el perfil, no tiene sentido el onboarding.
    if user.profile_completed:
        return redirect(_resolve_post_login_redirect(user))

    cuisine_tags, restriction_tags = _load_onboarding_tags()

    if request.method == "POST":
        try:
            name = validate_text(
                request.form.get("name", ""), "El nombre", min_length=2, max_length=50
            )
        except ValidationError as ex:
            flash(str(ex), "danger")
            selected_cuisines, selected_restrictions = _selected_tag_names(user)
            return render_template(
                "auth/onboarding.html",
                user=user,
                cuisine_tags=cuisine_tags,
                restriction_tags=restriction_tags,
                selected_cuisines=selected_cuisines,
                selected_restrictions=selected_restrictions,
            )

        uploaded_photo = request.files.get("foto")
        if uploaded_photo and uploaded_photo.filename:
            try:
                user.foto_perfil = _save_onboarding_photo(uploaded_photo)
            except ValueError as ex:
                flash(str(ex), "danger")
                selected_cuisines, selected_restrictions = _selected_tag_names(user)
                return render_template(
                    "auth/onboarding.html",
                    user=user,
                    cuisine_tags=cuisine_tags,
                    restriction_tags=restriction_tags,
                    selected_cuisines=selected_cuisines,
                    selected_restrictions=selected_restrictions,
                )

        cuisines = validate_tag_names(
            request.form.getlist("cuisines"), [tag.name for tag in cuisine_tags]
        )
        restrictions = validate_tag_names(
            request.form.getlist("restrictions"), [tag.name for tag in restriction_tags]
        )

        db.session.query(UserTags).filter(UserTags.user_id == user.user_id).delete(
            synchronize_session=False
        )
        selected_tags = (
            db.session.query(Tag)
            .filter(
                or_(
                    and_(Tag.category == TagCategory.COMIDA, Tag.name.in_(cuisines)),
                    and_(Tag.category == TagCategory.DIETA, Tag.name.in_(restrictions)),
                )
            )
            .all()
        )
        for tag in selected_tags:
            db.session.add(UserTags(user_id=user.user_id, id_tag=tag.id_tag))

        user.name = name
        user.profile_completed = True
        db.session.commit()

        flash("¡Listo! Tu perfil quedó configurado.", "success")
        return redirect(url_for("usuario.home"))

    selected_cuisines, selected_restrictions = _selected_tag_names(user)
    return render_template(
        "auth/onboarding.html",
        user=user,
        cuisine_tags=cuisine_tags,
        restriction_tags=restriction_tags,
        selected_cuisines=selected_cuisines,
        selected_restrictions=selected_restrictions,
    )


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
        try:
            username = validate_username(request.form.get("username", ""))
            password = validate_password(
                request.form.get("password", ""),
                field_label="La contraseña",
            )
        except ValidationError as ex:
            flash(str(ex), "warning")
            return render_template("auth/login_restaurante.html")
        user = ModelUser.login(db, username, password)
        if user:
            if user.role != Role.SOCIO_ADMIN.value:
                flash("Esta cuenta no puede iniciar sesión desde el acceso de restaurante.", "danger")
                return render_template("auth/login_restaurante.html")
            login_user(user)
            return redirect(_resolve_post_login_redirect(user))
        flash("Usuario o contraseña incorrectos.", "danger")
    return render_template("auth/login_restaurante.html")
