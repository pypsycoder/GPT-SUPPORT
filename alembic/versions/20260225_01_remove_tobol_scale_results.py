"""Remove TOBOL scale results from DB

Revision ID: 20260225_01
Revises: 20260223_02
Create Date: 2026-02-25

"""
from pathlib import Path
import json
import time

from alembic import op

revision = "20260225_01"
down_revision = "20260223_02"
branch_labels = None
depends_on = None

# region agent log
try:
    with (Path(__file__).resolve().parents[2] / "debug-88164a.log").open("a", encoding="utf-8") as _f:
        _f.write(
            json.dumps(
                {
                    "sessionId": "88164a",
                    "runId": "pre-fix",
                    "hypothesisId": "H2",
                    "location": "alembic/versions/20260225_01_remove_tobol_scale_results.py:revision-header",
                    "message": "loaded tobol removal migration header",
                    "data": {"revision": revision, "down_revision": down_revision},
                    "timestamp": int(time.time() * 1000),
                },
                ensure_ascii=False,
            )
            + "\n"
        )
except Exception:
    pass
# endregion


def upgrade() -> None:
    op.execute("DELETE FROM scales.scale_results WHERE scale_code = 'TOBOL'")


def downgrade() -> None:
    # Данные безвозвратно удалены — откат невозможен
    pass
