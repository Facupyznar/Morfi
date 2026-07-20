# Prompt 7 — Historial: opción de ver solo reservas futuras

## Objetivo
En el historial del comensal, poder filtrar para mostrar solo las reservas cuya
`fecha_hora` es posterior a la fecha/hora actual.

## Paso 0 — Inspección
| Qué revisar | Dónde | Para qué |
|---|---|---|
| `history` (hoy filtra por mes con `?month=`) | `app/routes/usuario/profile.py` (~L737) | Sumar el filtro de futuras sin romper el de mes |
| `_comparison_now_for_reservation` y manejo de timezone | `app/routes/usuario/profile.py` | Comparar `fecha_hora` correctamente |
| Template del historial | `app/templates/usuario/history.html` | Agregar el control (toggle/tab) |

## P1 — Backend
- Agregar un filtro simple (ej. query param `?proximas=1`) que, cuando está
  activo, limite la query a `Reserva.fecha_hora >= ahora`. Cuidar el timezone como
  ya lo hace el resto del archivo. Mantener el filtro por mes existente.

## P2 — Frontend
- En `history.html`, un control (toggle o pestaña) para alternar entre "Todas" y
  "Próximas", preservando el parámetro en la URL (coordinar con el prompt 5 si se
  hace después).

## Restricciones
- Sin comentarios en el código.
- Cambio mínimo; no reescribir `history`. Textos en español.

## Entregables
- Filtro de reservas futuras en `history`.
- Control en la UI para activarlo, con estado en la URL.
