-- 1. Eliminar tablas del esquema viejo (en orden por FK)
DROP TABLE IF EXISTS "Beneficio_plato" CASCADE;
DROP TABLE IF EXISTS "Beneficio" CASCADE;

-- 2. Eliminar tipos enum
DROP TYPE IF EXISTS beneficio_tipo CASCADE;
DROP TYPE IF EXISTS beneficio_aplica_a CASCADE;
DROP TYPE IF EXISTS beneficio_condicion_tipo CASCADE;
DROP TYPE IF EXISTS beneficio_valor_tipo CASCADE;

-- 3. Crear tipos enum nuevos
CREATE TYPE beneficio_condicion_tipo AS ENUM ('visitas');
CREATE TYPE beneficio_valor_tipo AS ENUM ('porcentaje', 'monto_fijo');

-- 4. Crear nueva tabla Beneficio
CREATE TABLE "Beneficio" (
    "Id"              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    "IdRestaurante"   UUID        NOT NULL REFERENCES "Restaurant"("IdRestaurant") ON DELETE CASCADE,
    "Descripcion"     TEXT        NOT NULL,
    "TipoCondicion"   beneficio_condicion_tipo NOT NULL DEFAULT 'visitas',
    "ValorCondicion"  INTEGER     NOT NULL,
    "TipoBeneficio"   beneficio_valor_tipo     NOT NULL,
    "ValorBeneficio"  NUMERIC(10,2) NOT NULL,
    "Activo"          BOOLEAN     NOT NULL DEFAULT TRUE,
    "CreatedAt"       TIMESTAMPTZ NOT NULL DEFAULT now()
);