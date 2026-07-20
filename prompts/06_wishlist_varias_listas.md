# Prompt 6 — Wishlist en varias listas nombradas

## Objetivo
Pasar de una única lista de favoritos a varias listas con nombre (ej. "Para
cumpleaños", "Con amigos"), permitiendo que **un mismo restaurante esté en varias
listas a la vez**.

## Problema de modelo (clave — leer antes de codear)
`User_favorites` tiene PK compuesta `(user_id, id_restaurante)` (ver
`app/models/user_favorites.py`), por lo que hoy un restaurante solo puede estar en
UNA fila por usuario → NO puede pertenecer a varias listas. La tabla `Wishlist` ya
existe (`app/models/wishlist.py`) pero el vínculo actual (`UserFavorites.wishlist_id`)
no alcanza para multi-lista. Hay que remodelar la relación restaurante↔lista a una
relación muchos-a-muchos.

## Paso 0 — Inspección
| Qué revisar | Dónde | Para qué |
|---|---|---|
| PK compuesta y `wishlist_id` | `app/models/user_favorites.py` | Entender la limitación actual |
| Tabla `Wishlist` ya existente | `app/models/wishlist.py` | Reusarla como cabecera de lista |
| Migración idempotente | `ensure_wishlist_schema` en `app/database.py` | Sumar la nueva estructura sin romper datos |
| Rutas actuales de favoritos/wishlist | buscar `favorite`/`wishlist` en `app/routes/**` | Ver el CRUD actual |
| UI actual | `app/templates/usuario/wishlist.html`, `app/templates/usuario/restaurant_detail.html` | Dónde elegir/mostrar listas |

## P0 — Modelo
- Introducir una relación muchos-a-muchos entre `Wishlist` y `Restaurant`
  (ej. nueva tabla `WishlistItem` con `wishlist_id` + `id_restaurante` y su propia
  PK/único), de modo que un restaurante pueda estar en varias listas.
- Mantener compatibilidad con los favoritos ya guardados (migrarlos a una lista
  por defecto "Guardados" o dejar `User_favorites` como esa lista default).
- Migración idempotente en `app/database.py` siguiendo el patrón `ensure_*`
  (crear tabla/índices solo si faltan, sin destruir datos).

## P1 — Rutas / servicios
- CRUD de listas: crear, renombrar y borrar listas del usuario.
- Agregar/quitar un restaurante a una o varias listas (toggle por lista).

## P2 — Templates
- `wishlist.html`: mostrar las listas con su nombre y sus restaurantes; permitir
  crear/renombrar/borrar listas.
- `restaurant_detail.html`: al guardar, poder elegir en qué lista(s) va el
  restaurante (selección múltiple).

## Restricciones
- Sin comentarios en el código.
- Simple y funcional; no sobre-diseñar.
- Migración que no rompa datos existentes. Textos en español.

## Entregables
- Modelo multi-lista + migración idempotente.
- CRUD de listas y asignación de un restaurante a varias listas.
- UI de listas en wishlist y selector de listas al guardar un restaurante.
