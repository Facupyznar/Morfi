-- Morfi — Migración: campos nuevos en Restaurant
-- Correr UNA SOLA VEZ con: psql -d <tu_db> -f migration.sql
-- (o pegarlo directamente en psql / DBeaver / pgAdmin)

ALTER TABLE "Restaurant"
    ADD COLUMN IF NOT EXISTS "Descripcion"  TEXT,
    ADD COLUMN IF NOT EXISTS "PrecioRango"  VARCHAR(5),
    ADD COLUMN IF NOT EXISTS "CoverUrl"     VARCHAR(255),
    ADD COLUMN IF NOT EXISTS "LogoUrl"      VARCHAR(255),
    ADD COLUMN IF NOT EXISTS "GalleryJson"  TEXT,
    ADD COLUMN IF NOT EXISTS "Telefono"     VARCHAR(30),
    ADD COLUMN IF NOT EXISTS "SitioWeb"     VARCHAR(200),
    ADD COLUMN IF NOT EXISTS "Instagram"    VARCHAR(60);