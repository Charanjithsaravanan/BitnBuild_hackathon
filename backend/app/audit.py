from sqlalchemy.orm import Session

from .models import AuditEvent, User


def audit(db: Session, *, user: User | None, action: str, resource_type: str | None = None,
          resource_id: str | None = None, context: dict | None = None) -> None:
    row = AuditEvent(
        user_id=user.id if user else None,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=(context or {}).get("ip_address"),
        user_agent=(context or {}).get("user_agent"),
        metadata_json=context,
    )
    db.add(row)
