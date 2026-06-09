"""Extensiones de seguridad compartidas.

Se centraliza la instancia de CSRFProtect para poder eximir vistas puntuales
(p. ej. el callback de OAuth de Google) con el decorador @csrf.exempt desde
los módulos de rutas, manteniendo una única instancia inicializada en run.py.
"""
from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect()
