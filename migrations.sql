-- Morfi — Migración: campos nuevos en Restaurant
-- Correr UNA SOLA VEZ con:  ❯ docker compose exec -u postgres <Nombre_db> psql -d <Nombre_db>


ALTER TABLE "Restaurant"
    ADD COLUMN IF NOT EXISTS "Descripcion"  TEXT,
    ADD COLUMN IF NOT EXISTS "PrecioRango"  VARCHAR(5),
    ADD COLUMN IF NOT EXISTS "CoverUrl"     VARCHAR(255),
    ADD COLUMN IF NOT EXISTS "LogoUrl"      VARCHAR(255),
    ADD COLUMN IF NOT EXISTS "GalleryJson"  TEXT,
    ADD COLUMN IF NOT EXISTS "Telefono"     VARCHAR(30),
    ADD COLUMN IF NOT EXISTS "SitioWeb"     VARCHAR(200),
    ADD COLUMN IF NOT EXISTS "Instagram"    VARCHAR(60);

--migracion nueva para menu
ALTER TABLE "Menu" ADD COLUMN IF NOT EXISTS "FotoUrl" VARCHAR(255);

--migracion nueva para listas de wishlist
CREATE TABLE IF NOT EXISTS "Wishlist" (
    "Id"         UUID PRIMARY KEY,
    "UserID"     UUID NOT NULL REFERENCES "User"("user_id") ON DELETE CASCADE,
    "Nombre"     VARCHAR(60) NOT NULL,
    "Created_at" TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE "User_favorites"
    ADD COLUMN IF NOT EXISTS "WishlistId" UUID REFERENCES "Wishlist"("Id") ON DELETE SET NULL;

--para salir despues es /q