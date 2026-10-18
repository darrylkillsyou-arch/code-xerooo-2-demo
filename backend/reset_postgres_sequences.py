from sqlalchemy import text
from app.database import engine

sql = """
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN
        SELECT
            t.table_name,
            c.column_name,
            pg_get_serial_sequence(
                quote_ident(t.table_name),
                c.column_name
            ) AS seq
        FROM information_schema.tables t
        JOIN information_schema.table_constraints tc
            ON tc.table_name = t.table_name
            AND tc.constraint_type = 'PRIMARY KEY'
        JOIN information_schema.key_column_usage c
            ON c.constraint_name = tc.constraint_name
            AND c.table_name = tc.table_name
        WHERE t.table_schema = 'public'
    LOOP
        IF r.seq IS NOT NULL THEN
            EXECUTE format(
                'SELECT setval(%L, COALESCE((SELECT MAX(%I) FROM %I), 1), true)',
                r.seq,
                r.column_name,
                r.table_name
            );
        END IF;
    END LOOP;
END $$;
"""

with engine.begin() as conn:
    conn.execute(text(sql))

print("Postgres sequences reset successfully.")