from __future__ import annotations

import os
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from dotenv import load_dotenv
from sqlalchemy import create_engine, text


BASE_DIR = Path(__file__).resolve().parents[1]


def _load_database_url() -> str:
    env_path = BASE_DIR / ".env"
    load_dotenv(env_path)
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is not configured in .env")
    return url.replace("+asyncpg", "+psycopg")


def main() -> None:
    database_url = _load_database_url()

    alembic_cfg = Config(str(BASE_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))
    script = ScriptDirectory.from_config(alembic_cfg)
    head_revision = script.get_current_head()

    engine = create_engine(database_url)
    with engine.connect() as conn:
        db_revision = conn.execute(text("SELECT version_num FROM public.alembic_version")).scalar()

    pending = []
    if db_revision != head_revision:
        pending = [
            revision.revision
            for revision in reversed(list(script.walk_revisions(base=db_revision, head=head_revision)))
        ]

    print(f"DB revision:   {db_revision}")
    print(f"Code head:     {head_revision}")
    print(f"In sync:       {'yes' if db_revision == head_revision else 'no'}")
    if pending:
        print("Pending path:")
        for revision in pending:
            print(f"  - {revision}")


if __name__ == "__main__":
    main()
