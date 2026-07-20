# Prompt 2 — Marcar una notificación como leída (individual)

## Objetivo
Hoy solo existe un endpoint que marca TODAS las notificaciones como leídas. Falta
uno que marque UNA sola, para dispararlo al hacer click en la notificación.

## Paso 0 — Inspección
| Qué revisar | Dónde | Para qué |
|---|---|---|
| `mark_notifications_read` (marca todas) y `_serialize` (expone `id`) | `app/routes/usuario/notifications.py` | Copiar patrón y responder JSON |
| Render de items y campanita/dropdown | `app/templates/usuario/notifications.html` | Dónde enganchar el click |
| `notifications_dropdown` (contador `unread`) | `app/routes/usuario/notifications.py` | Actualizar el badge tras leer |

## P1 — Backend
- Nuevo endpoint `POST /notificaciones/<uuid:id_notification>/leer` que:
  - valide que la notificación sea del `current_user`,
  - la marque `leida = True` y commitee,
  - devuelva JSON `{ok: true, unread: <nuevo contador de no leídas>}`.

## P2 — Frontend
- En `notifications.html` (página y dropdown): al hacer click en una notificación,
  hacer `fetch` POST al nuevo endpoint, marcarla visualmente como leída y
  actualizar el badge de no leídas con el `unread` devuelto. Después seguir al
  `url_destino` si corresponde. Reusar el patrón `fetch` ya usado en el archivo.

## Restricciones
- Sin comentarios en el código.
- Simple y funcional. Textos en español.
- No tocar el comportamiento del "marcar todas".

## Entregables
- Endpoint de leído individual.
- Click en una notificación la marca leída sin recargar y ajusta el contador.
