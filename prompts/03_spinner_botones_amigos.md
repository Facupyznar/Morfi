# Prompt 3 — Spinner en botones de solicitud (amigos)

## Objetivo
Al enviar una solicitud de amistad, deshabilitar el botón y mostrar un
`spinner-border` mientras se espera la respuesta del servidor. Mismo patrón que ya
se usa en el asistente de IA.

## Paso 0 — Inspección
| Qué revisar | Dónde | Para qué |
|---|---|---|
| Submit AJAX que ya hace `button.disabled = true` (falta spinner) | `app/templates/usuario/friends.html` (~L370) | Agregar el spinner ahí |
| Patrón de spinner-border existente | `app/templates/restaurante/asistente.html` | Copiar exactamente el mismo markup/clases |
| Botones "Conectar" en la pantalla de descubrir | `app/templates/usuario/discover_friends.html` | Aplicar el mismo patrón |

## P2 — Frontend
- En el handler de submit de las solicitudes: al enviar, guardar el `innerHTML`
  original del botón, reemplazarlo por el `spinner-border` (mismas clases que el
  asistente) y deshabilitarlo. Al terminar (éxito o error), restaurar el estado.
- Aplicar el mismo cambio en `discover_friends.html` si tiene botones de conectar.

## Restricciones
- Sin comentarios en el código.
- Reusar clases/markup del spinner ya existente; no inventar CSS nuevo.
- Textos en español.

## Entregables
- Botones de solicitud con spinner + disabled mientras esperan respuesta, en
  `friends.html` y `discover_friends.html`.
