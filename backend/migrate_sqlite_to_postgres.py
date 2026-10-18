from sqlalchemy import create_engine, MetaData, Table, select
from sqlalchemy.orm import sessionmaker
from app.database import engine as pg_engine
from app.database import Base

SQLITE_URL = "sqlite:///./maccall.db"

sqlite_engine = create_engine(
    SQLITE_URL,
    connect_args={"check_same_thread": False}
)

Base.metadata.create_all(bind=pg_engine)

sqlite_meta = MetaData()
sqlite_meta.reflect(bind=sqlite_engine)

pg_meta = MetaData()
pg_meta.reflect(bind=pg_engine)

with sqlite_engine.connect() as src_conn, pg_engine.begin() as dst_conn:
    for table_name in sqlite_meta.sorted_tables:
        name = table_name.name

        if name not in pg_meta.tables:
            print(f"Skipping missing destination table: {name}")
            continue

        src_table = sqlite_meta.tables[name]
        dst_table = pg_meta.tables[name]

        rows = src_conn.execute(select(src_table)).mappings().all()

        if not rows:
            print(f"{name}: 0 rows")
            continue

        dst_conn.execute(dst_table.insert(), rows)
        print(f"{name}: migrated {len(rows)} rows")

print("Migration complete.")