from sqlalchemy import inspect, text

from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


def init_db(app):
    db.init_app(app)


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
