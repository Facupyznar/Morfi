# Prompt 5 — Guardar la tab activa en la URL

## Objetivo
Que las pantallas con pestañas recuerden la tab activa en la URL (como ya hace
notificaciones con `?filtro=`), para que al recargar o volver no se pierda.

## Paso 0 — Inspección (auditar primero)
| Qué revisar | Dónde | Para qué |
|---|---|---|
| Patrón ya resuelto con `?filtro=` | `app/routes/usuario/notifications.py`, `app/templates/usuario/notifications.html` | Copiar el mismo enfoque |
| Pantallas con tabs Bootstrap | Buscar `data-bs-toggle="tab"` / `nav-tabs` / `nav-pills` en `app/templates/**` | Detectar cuáles NO persisten la tab |

Ejecutá una búsqueda de tabs en todos los templates y listá cuáles ya persisten y
cuáles no (candidatos: amigos, panel de restaurante, wishlist). Reportalo antes de
tocar código.

## P2 — Frontend (para cada pantalla con tabs que no lo haga)
- Al cargar, leer el query param (ej. `?tab=`) y activar esa pestaña.
- Al cambiar de pestaña, actualizar la URL con `history.replaceState` sin recargar.
- Respetar la tab por defecto cuando no hay parámetro.

## Restricciones
- Sin comentarios en el código.
- No romper el default ni el `?filtro=` de notificaciones.
- Solución uniforme entre pantallas; textos en español.

## Entregables
- Listado de pantallas con tabs y su estado.
- Persistencia de la tab activa en la URL en las que faltaban.
