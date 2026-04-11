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

--para salir despues es /q