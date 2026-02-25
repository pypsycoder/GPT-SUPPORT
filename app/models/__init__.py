"""Common SQLAlchemy declarative base and model registrations."""

from sqlalchemy.orm import declarative_base


Base = declarative_base()

# Import ORM models so that their metadata is registered on Base during startup.
# These imports are intentionally kept at module level to ensure ``Base.metadata``
# is aware of every table when ``create_all`` is executed.
from app.users import models as users_models  # noqa: F401
from app.researchers import models as researchers_models  # noqa: F401
from app.auth import models as auth_models  # noqa: F401
from app.scales import models as scales_models  # noqa: F401
from app.vitals import models as vitals_models  # noqa: F401
from app.education import models as education_models  # noqa: F401
from app.dialysis import models as dialysis_models  # noqa: F401
from app.sleep_tracker import models as sleep_tracker_models  # noqa: F401
from app.routine import models as routine_models  # noqa: F401
from app.medications import models as medications_models  # noqa: F401
from app.practices import models as practices_models  # noqa: F401


__all__ = [
    "Base",
]
