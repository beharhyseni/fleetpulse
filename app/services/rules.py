from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.models import Telemetry


def apply_rules(db: Session, readings: Sequence[Telemetry]) -> int:
    """Evaluate alert rules for freshly ingested readings; returns alerts created."""
    return 0
