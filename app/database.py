from sqlalchemy import inspect, text

from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


def init_db(app):
    db.init_app(app)


def ensure_user_schema():
    """Migración idempotente para el login con Google sobre la tabla User.

    Agrega google_id / avatar_url / profile_completed y relaja restricciones
    NOT NULL en password y dirección/coordenadas. No destruye datos existentes.
    """
    inspector = inspect(db.engine)
    if "User" not in inspector.get_table_names():
        return

    columns = {column["name"]: column for column in inspector.get_columns("User")}

    # La contraseña pasa a ser opcional (usuarios de Google no tienen hash).
    if columns.get("password", {}).get("nullable") is False:
        db.session.execute(text('ALTER TABLE "User" ALTER COLUMN "password" DROP NOT NULL'))

    if "google_id" not in columns:
        db.session.execute(text('ALTER TABLE "User" ADD COLUMN "google_id" VARCHAR(255)'))
        db.session.execute(
            text('CREATE UNIQUE INDEX IF NOT EXISTS "ix_User_google_id" ON "User" ("google_id")')
        )

    if "avatar_url" not in columns:
        db.session.execute(text('ALTER TABLE "User" ADD COLUMN "avatar_url" VARCHAR(512)'))

    if "profile_completed" not in columns:
        # Usuarios ya existentes completaron su registro → TRUE.
        db.session.execute(
            text('ALTER TABLE "User" ADD COLUMN "profile_completed" BOOLEAN NOT NULL DEFAULT TRUE')
        )
        # Los nuevos registros (incluido Google) definen el valor explícitamente.
        db.session.execute(text('ALTER TABLE "User" ALTER COLUMN "profile_completed" SET DEFAULT FALSE'))

    # Dirección y coordenadas opcionales para el alta por Google.
    for column_name in ("address", "latitude", "longitude"):
        if columns.get(column_name, {}).get("nullable") is False:
            db.session.execute(
                text(f'ALTER TABLE "User" ALTER COLUMN "{column_name}" DROP NOT NULL')
            )

    # Flag de descubribilidad por contactos (default TRUE para todos).
    if "discoverable_by_contacts" not in columns:
        db.session.execute(
            text('ALTER TABLE "User" ADD COLUMN "discoverable_by_contacts" BOOLEAN NOT NULL DEFAULT TRUE')
        )

    db.session.commit()


def ensure_wishlist_schema():
    """Migración idempotente para las listas de wishlist.

    La tabla ``Wishlist`` la crea ``db.create_all()``; acá solo agregamos la
    columna ``WishlistId`` a ``User_favorites`` (NULL = lista por defecto).
    """
    inspector = inspect(db.engine)
    if "User_favorites" not in inspector.get_table_names():
        return

    column_names = {column["name"] for column in inspector.get_columns("User_favorites")}

    if "WishlistId" not in column_names:
        db.session.execute(
            text(
                'ALTER TABLE "User_favorites" '
                'ADD COLUMN "WishlistId" UUID '
                'REFERENCES "Wishlist"("Id") ON DELETE SET NULL'
            )
        )

    db.session.commit()


def ensure_menu_schema():
    inspector = inspect(db.engine)
    if "Menu" not in inspector.get_table_names():
        return

    column_names = {column["name"] for column in inspector.get_columns("Menu")}

    if "Descripcion" not in column_names:
        db.session.execute(text('ALTER TABLE "Menu" ADD COLUMN "Descripcion" TEXT'))

    if "Categoria" not in column_names:
        db.session.execute(text('ALTER TABLE "Menu" ADD COLUMN "Categoria" VARCHAR(50)'))

    # Preserve legacy descriptions saved in the old Tags column.
    if "Tags" in column_names:
        db.session.execute(
            text(
                'UPDATE "Menu" '
                'SET "Descripcion" = "Tags" '
                'WHERE "Tags" IS NOT NULL AND ("Descripcion" IS NULL OR "Descripcion" = \'\')'
            )
        )

    # Backfill the explicit category from existing tag relations.
    db.session.execute(
        text(
            'UPDATE "Menu" AS m '
            'SET "Categoria" = sub.name '
            'FROM ('
            '    SELECT DISTINCT ON (mt."IdPlato") mt."IdPlato" AS id_plato, t."Name" AS name '
            '    FROM "Menu_tags" AS mt '
            '    JOIN "Tag" AS t ON t."IdTag" = mt."IdTag" '
            '    WHERE t."Category" = \'COMIDA\' '
            '    ORDER BY mt."IdPlato", t."Name"'
            ') AS sub '
            'WHERE m."IdPlato" = sub.id_plato '
            'AND (m."Categoria" IS NULL OR m."Categoria" = \'\')'
        )
    )
    db.session.commit()
