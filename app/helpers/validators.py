import json
import os
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse


class ValidationError(ValueError):
    pass


EMAIL_RE = re.compile(r"^[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}$", re.IGNORECASE)
USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,40}$")
PHONE_RE = re.compile(r"^[0-9+() \-]{8,20}$")
INSTAGRAM_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}$")


def validate_text(value, field_label, *, required=True, min_length=None, max_length=None):
    normalized = (value or "").strip()
    if required and not normalized:
        raise ValidationError(f"{field_label} es obligatorio.")
    if normalized and min_length is not None and len(normalized) < min_length:
        raise ValidationError(f"{field_label} debe tener al menos {min_length} caracteres.")
    if normalized and max_length is not None and len(normalized) > max_length:
        raise ValidationError(f"{field_label} no puede superar los {max_length} caracteres.")
    return normalized


def validate_email(value, field_label="El email"):
    email = validate_text(value, field_label, min_length=5, max_length=255).lower()
    if not EMAIL_RE.match(email):
        raise ValidationError(f"{field_label} no tiene un formato válido.")
    return email


def validate_username(value, field_label="El nombre de usuario"):
    username = validate_text(value, field_label, min_length=3, max_length=100)
    if not USERNAME_RE.match(username):
        raise ValidationError(
            f"{field_label} solo puede contener letras, números, puntos, guiones y guiones bajos."
        )
    return username


def validate_password(value, *, min_length=5, field_label="La contraseña"):
    password = value or ""
    if len(password) < min_length:
        raise ValidationError(f"{field_label} debe tener al menos {min_length} caracteres.")
    return password


def validate_password_confirmation(password, confirmation):
    if password != confirmation:
        raise ValidationError("Las contraseñas no coinciden.")


def validate_birth_date(value, *, min_age=10):
    raw_value = validate_text(value, "La fecha de nacimiento")
    try:
        parsed = datetime.strptime(raw_value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValidationError("La fecha de nacimiento no tiene un formato válido.") from exc

    today = date.today()
    if parsed > today:
        raise ValidationError("La fecha de nacimiento no puede ser futura.")

    age = today.year - parsed.year
    if (today.month, today.day) < (parsed.month, parsed.day):
        age -= 1
    if age < min_age:
        raise ValidationError(f"Debés tener al menos {min_age} años.")
    return parsed


def validate_int(value, field_label, *, min_value=None, max_value=None, required=True):
    raw_value = (value or "").strip()
    if not raw_value:
        if required:
            raise ValidationError(f"{field_label} es obligatorio.")
        return None
    try:
        parsed = int(raw_value)
    except ValueError as exc:
        raise ValidationError(f"{field_label} debe ser un número entero válido.") from exc
    if min_value is not None and parsed < min_value:
        raise ValidationError(f"{field_label} debe ser mayor o igual a {min_value}.")
    if max_value is not None and parsed > max_value:
        raise ValidationError(f"{field_label} debe ser menor o igual a {max_value}.")
    return parsed


def validate_decimal(value, field_label, *, min_value=None, required=True):
    raw_value = (value or "").strip()
    if not raw_value:
        if required:
            raise ValidationError(f"{field_label} es obligatorio.")
        return None
    try:
        parsed = Decimal(raw_value)
    except (InvalidOperation, TypeError) as exc:
        raise ValidationError(f"{field_label} debe ser un número válido.") from exc
    if min_value is not None and parsed < Decimal(str(min_value)):
        raise ValidationError(f"{field_label} debe ser mayor o igual a {min_value}.")
    return parsed


def validate_choice(value, field_label, allowed_values, *, required=True):
    normalized = (value or "").strip()
    if not normalized:
        if required:
            raise ValidationError(f"{field_label} es obligatorio.")
        return None
    if normalized not in allowed_values:
        raise ValidationError(f"{field_label} no es válido.")
    return normalized


def validate_phone(value, field_label="El teléfono"):
    phone = validate_text(value, field_label, required=False, max_length=30)
    if phone and not PHONE_RE.match(phone):
        raise ValidationError(f"{field_label} no tiene un formato válido.")
    return phone or None


def validate_url(value, field_label="El sitio web"):
    raw_url = validate_text(value, field_label, required=False, max_length=200)
    if not raw_url:
        return None
    normalized = raw_url if "://" in raw_url else f"https://{raw_url}"
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or "." not in parsed.netloc:
        raise ValidationError(f"{field_label} no tiene un formato válido.")
    return normalized


def validate_instagram(value, field_label="El usuario de Instagram"):
    raw_value = validate_text(value, field_label, required=False, max_length=60)
    if not raw_value:
        return None
    normalized = raw_value.lstrip("@")
    if not INSTAGRAM_RE.match(normalized):
        raise ValidationError(f"{field_label} no es válido.")
    return normalized


def validate_image_file(uploaded_file, *, field_label="La imagen", allowed_extensions=None, max_size_mb=5):
    if not uploaded_file or not getattr(uploaded_file, "filename", ""):
        return
    _, extension = os.path.splitext(uploaded_file.filename.lower())
    allowed_extensions = allowed_extensions or {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    if extension not in allowed_extensions:
        allowed_values = ", ".join(sorted(ext.replace(".", "").upper() for ext in allowed_extensions))
        raise ValidationError(f"{field_label} debe ser {allowed_values}.")

    current_pos = uploaded_file.stream.tell()
    uploaded_file.stream.seek(0, os.SEEK_END)
    size_bytes = uploaded_file.stream.tell()
    uploaded_file.stream.seek(current_pos)
    if size_bytes > max_size_mb * 1024 * 1024:
        raise ValidationError(f"{field_label} no puede superar los {max_size_mb}MB.")


def validate_file(uploaded_file, *, field_label="El archivo", allowed_extensions=None, max_size_mb=5):
    if not uploaded_file or not getattr(uploaded_file, "filename", ""):
        return
    _, extension = os.path.splitext(uploaded_file.filename.lower())
    allowed_extensions = allowed_extensions or set()
    if allowed_extensions and extension not in allowed_extensions:
        allowed_values = ", ".join(sorted(ext.replace(".", "").upper() for ext in allowed_extensions))
        raise ValidationError(f"{field_label} debe ser {allowed_values}.")

    current_pos = uploaded_file.stream.tell()
    uploaded_file.stream.seek(0, os.SEEK_END)
    size_bytes = uploaded_file.stream.tell()
    uploaded_file.stream.seek(current_pos)
    if size_bytes > max_size_mb * 1024 * 1024:
        raise ValidationError(f"{field_label} no puede superar los {max_size_mb}MB.")


def validate_schedule_json(value):
    raw_value = (value or "[]").strip()
    try:
        parsed = json.loads(raw_value)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValidationError("El horario no tiene un formato válido.") from exc

    if not isinstance(parsed, list):
        raise ValidationError("El horario no tiene un formato válido.")

    for slot in parsed:
        if not isinstance(slot, dict):
            raise ValidationError("El horario no tiene un formato válido.")
        active = bool(slot.get("active"))
        if active:
            open_time = str(slot.get("open") or "")
            close_time = str(slot.get("close") or "")
            if not TIME_RE.match(open_time) or not TIME_RE.match(close_time):
                raise ValidationError("Todos los horarios activos deben tener una hora válida.")
    return parsed


def validate_tag_names(selected_values, allowed_values):
    allowed_lookup = set(allowed_values)
    normalized = []
    for value in selected_values:
        cleaned = (value or "").strip()
        if cleaned and cleaned in allowed_lookup:
            normalized.append(cleaned)
    return normalized
