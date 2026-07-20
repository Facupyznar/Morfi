# Prompt 1 — Confirmación de asistencia por QR

## Objetivo
Cada reserva confirmada muestra un código QR al comensal. El restaurante abre una
pantalla con la cámara del celular, escanea el QR y eso marca la reserva como
**COMPLETADA** (asistencia). Se usa el campo `token_validacion` que ya existe en
el modelo `Reserva`.

## Decisión de estado (importante)
La reserva se crea directamente en estado `CONFIRMADA` (ver `crear_reserva` en
`app/routes/usuario/home.py`), así que escanear NO debe volver a "confirmar":
debe marcar `ReservaStatus.COMPLETADA`, que es lo que significa "confirmar la
asistencia". No agregues estados nuevos al enum.

## Paso 0 — Inspección (antes de escribir código)
Revisá y respetá estas convenciones. NO escribas código hasta completar esto:

| Qué revisar | Dónde | Para qué |
|---|---|---|
| Campo `token_validacion` (String(150), unique) y estados | `app/models/reserva.py`, `app/models/enums.py` | Reusar el token; marcar COMPLETADA |
| `crear_reserva` (hoy NO setea `token_validacion`) | `app/routes/usuario/home.py` (~L511) | Generar el token al crear la reserva |
| `reserva_confirmada` y su template | `app/routes/usuario/home.py` (~L619), `app/templates/usuario/reserva_confirmada.html` | Dónde mostrar el QR |
| Endpoints AJAX del socio y su patrón (JSON, `_admin_required`, `_get_owned_restaurant`) | `app/routes/restaurante/reservas_routes.py` | Copiar el patrón para el endpoint de validación |
| Uso de `csrf.exempt` y del blueprint restaurante | `app/routes/restaurante/reservas_routes.py`, `app/helpers/security.py` | Manejar CSRF del POST de escaneo |
| Bloques de CSS/JS y CDN | `app/templates/base.html`, `app/templates/usuario/reserva_confirmada.html` | Cómo se cargan librerías por CDN |

## P0 — Datos / token
- En `crear_reserva`, al construir la `Reserva`, setear `token_validacion` con un
  valor único (ej. `uuid.uuid4().hex`). No cambies el modelo.
- En `reserva_confirmada`, si la reserva no tiene `token_validacion` (reservas
  viejas), generarlo y commitear antes de mostrar el QR.

## P1 — Backend
- Dependencia: agregar `qrcode[pil]` a `requirements.txt`.
- Comensal: en `reserva_confirmada`, generar el PNG del QR en memoria a partir de
  `token_validacion`, codificarlo en base64 y pasarlo al template como data URI.
- Restaurante: agregar al blueprint restaurante (en `reservas_routes.py`):
  - `GET /restaurante/checkin` → pantalla del escáner (solo `SOCIO_ADMIN`).
  - `POST /restaurante/checkin/validar` → recibe el `token`, busca la `Reserva`
    por `token_validacion`, valida que pertenezca al restaurante del socio
    (`_get_owned_restaurant`), la marca `COMPLETADA`, commitea y devuelve JSON
    `{ok, mensaje, cliente, hora}`. Si el token no existe o no es de su local,
    devolver JSON de error con status apropiado. Manejar CSRF como el resto de
    endpoints AJAX del socio.

## P2 — Templates / estáticos
- `app/templates/usuario/reserva_confirmada.html`: mostrar el QR (data URI) con un
  texto tipo "Mostrá este código en el restaurante".
- Nuevo `app/templates/restaurante/checkin.html`: cargar `html5-qrcode` por CDN,
  abrir la cámara trasera, y al leer un QR hacer `fetch` POST a
  `/restaurante/checkin/validar` mostrando el resultado (éxito/error) en pantalla.
  Reutilizar el estilo visual existente del panel de restaurante.
- Agregar un acceso al escáner desde la pantalla de reservas del socio
  (`app/templates/restaurante/reservas.html`).

## Restricciones
- Sin comentarios en el código.
- Código simple pero funcional; nada de abstracciones de más.
- Textos visibles en español.
- No romper el flujo de reserva existente ni el de cambio de estado del socio.
- Reutilizar helpers, blueprint y patrones AJAX ya presentes.

## Entregables esperados
- `requirements.txt` con `qrcode[pil]`.
- `token_validacion` seteado en creación y garantizado en la pantalla de éxito.
- QR visible para el comensal.
- Pantalla de escáner del socio + endpoint de validación que marca COMPLETADA.
- Acceso al escáner desde la vista de reservas.
