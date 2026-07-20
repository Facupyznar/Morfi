# Prompt 8 — Mostrar beneficios/descuentos en la reserva

## Objetivo
Mostrar los beneficios activos de un restaurante (modelo `Beneficio`, ya existe y
está en el seed) en la pantalla de detalle del restaurante y/o en el wizard de
reserva, para que el comensal los vea.

## Paso 0 — Inspección
| Qué revisar | Dónde | Para qué |
|---|---|---|
| Modelo `Beneficio` (`activo`, `id_restaurante`, `tipo_condicion`, `valor_condicion`, `tipo_beneficio`, `valor_beneficio`) | `app/models/beneficio.py`, `app/models/enums.py` | Saber qué campos mostrar |
| Cómo el socio los formatea/lista | `app/routes/restaurante/beneficios_routes.py`, `app/templates/restaurante/beneficios.html` | Reusar formato (% vs monto fijo, condición por visitas) |
| `restaurant_detail` y `reserva_wizard` | `app/routes/usuario/home.py` (~L288 y ~L417) | Dónde inyectar los beneficios |
| Templates destino | `app/templates/usuario/restaurant_detail.html`, `app/templates/usuario/reserva_wizard.html` | Dónde renderizarlos |

## P1 — Backend
- En `restaurant_detail` (y/o `reserva_wizard`), consultar los `Beneficio` con
  `activo = True` del restaurante y pasarlos al template. Sin lógica de
  elegibilidad nueva: solo listarlos.

## P2 — Templates
- Renderizar cada beneficio con su descripción, la condición (ej. "a las N
  visitas") y el valor formateado (porcentaje o monto fijo según
  `tipo_beneficio`). Reusar estilos existentes de las tarjetas del detalle.
- Si no hay beneficios activos, no mostrar la sección.

## Restricciones
- Sin comentarios en el código.
- Simple y funcional; solo visualización, sin tocar el flujo de reserva.
- Textos en español.

## Entregables
- Beneficios activos visibles en el detalle del restaurante (y wizard si aplica),
  con formato correcto de valor y condición.
