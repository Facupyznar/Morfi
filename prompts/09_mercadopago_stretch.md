# Prompt 9 — Mercado Pago (stretch, hacer al final)

## Aviso
Es el caso más riesgoso: depende de una cuenta y credenciales de sandbox de
Mercado Pago que todavía no están creadas, y de una integración externa (checkout
+ confirmación de pago). Hacerlo último. Si no llega para la entrega, se deja
afuera y se justifica como decisión consciente de tiempo. Todo el feature debe
quedar **detrás de un flag de configuración**: si no hay credenciales, la app
funciona igual que hoy y el pago no aparece.

## Prerrequisitos (fuera del código, hace Claudio)
- Crear cuenta de Mercado Pago y app en el panel de desarrolladores.
- Obtener credenciales de **sandbox** (Access Token de prueba).
- Cargarlas como variables de entorno (no hardcodear, no commitear).

## Paso 0 — Inspección
| Qué revisar | Dónde | Para qué |
|---|---|---|
| Flujo actual de creación de reserva | `app/routes/usuario/home.py` (`crear_reserva`, `reserva_wizard`, `reserva_confirmada`) | Dónde engancha el pago |
| Manejo de config y env vars | `app/config.py` | Sumar credenciales MP con flag |
| Patrón de rutas del blueprint usuario y CSRF | `app/routes/usuario/`, `app/helpers/security.py` | Callbacks/webhook sin romper CSRF |
| Notificaciones in-app | `app/routes/usuario/notifications.py` (`crear_notificacion`) | Avisar pago aprobado |

## P0 — Config
- Agregar en `Config` las credenciales de MP leídas de env (Access Token) y un
  flag calculado tipo `MP_ENABLED = bool(access_token)`.
- Dependencia: agregar el SDK `mercadopago` a `requirements.txt`.

## P1 — Backend
- Servicio que crea una preferencia de Checkout Pro para una reserva (título,
  precio, `back_urls`, `external_reference` = id de la reserva).
- Endpoint que inicia el pago y redirige al checkout de MP.
- Endpoint de retorno/confirmación (`back_urls`) y/o webhook que verifica el
  estado del pago y, si está aprobado, lo registra y notifica al comensal.
- Todo condicionado a `MP_ENABLED`: si está apagado, estos endpoints/opciones no
  se exponen y el flujo de reserva queda intacto.

## P2 — Templates
- En el wizard/detalle: mostrar el botón de "Pagar con Mercado Pago" solo si
  `MP_ENABLED`. Pantalla simple de resultado (aprobado / pendiente / rechazado).

## Restricciones
- Sin comentarios en el código.
- Aislado y opcional: si MP no está configurado, nada cambia respecto de hoy.
- No commitear credenciales. Textos en español.

## Entregables
- Integración de Checkout Pro detrás de flag, con creación de preferencia,
  redirect, confirmación/webhook y notificación de pago aprobado.
- Si no se completa a tiempo: dejar el flag apagado y documentar la decisión en la
  presentación técnica.
