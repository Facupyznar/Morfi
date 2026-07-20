# Prompt 4 — Refrescar el listado de amigos al enviar una solicitud

## Objetivo
Al mandar una solicitud de amistad, el estado en pantalla debe quedar consistente
sin recargar la página (que la persona no tenga que refrescar para ver el cambio).

## Paso 0 — Inspección (auditar primero, después implementar)
| Qué revisar | Dónde | Para qué |
|---|---|---|
| `connect_friend` (¿devuelve JSON?, ¿qué campos?) | `app/routes/usuario/profile.py` (~L477) | Saber qué responde el POST |
| `friends` (arma listas: amigos, pendientes, conectables) | `app/routes/usuario/profile.py` (~L864) | Ver de dónde salen las listas |
| Submit AJAX (hoy remueve la card al éxito) | `app/templates/usuario/friends.html` (~L370) | Ver qué se actualiza y qué no |
| Pantalla de descubrir | `app/templates/usuario/discover_friends.html` | Mismo comportamiento |

Primero reportá en un comentario del PR (no en el código) qué queda desactualizado
hoy tras enviar una solicitud. Después implementá el mínimo necesario.

## P1 — Backend (solo si hace falta)
- Si el frontend necesita datos frescos, exponer un endpoint JSON que devuelva las
  listas actualizadas (conectables y/o solicitudes enviadas) para el usuario
  actual. Reusar la lógica de `friends`, sin duplicarla de más.

## P2 — Frontend
- Tras un POST de "Conectar" con respuesta OK: reflejar el cambio en el acto
  (mover la card a "solicitud enviada"/pendiente o re-pedir la lista por JS y
  re-renderizar). Sin recargar la página.

## Restricciones
- Sin comentarios en el código.
- Simple y funcional; no re-arquitecturar la pantalla de amigos.
- Textos en español.

## Entregables
- Reporte breve de qué quedaba desactualizado.
- Estado de amigos/solicitudes consistente tras enviar, sin refrescar.
