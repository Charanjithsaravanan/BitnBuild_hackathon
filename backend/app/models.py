from datetime import datetime, timezone
import hashlib
import uuid

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


def hash_participant_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    experiments: Mapped[list["Experiment"]] = relationship(back_populates="owner", cascade="all, delete-orphan")


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_version: Mapped[int | None] = mapped_column(Integer, nullable=True)

    owner: Mapped[User] = relationship(back_populates="experiments")
    versions: Mapped[list["ExperimentVersion"]] = relationship(back_populates="experiment", cascade="all, delete-orphan")
    sessions: Mapped[list["ParticipantSession"]] = relationship(back_populates="experiment", cascade="all, delete-orphan")


class ExperimentVersion(Base):
    __tablename__ = "experiment_versions"
    __table_args__ = (UniqueConstraint("experiment_id", "version", name="uq_experiment_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    definition: Mapped[dict] = mapped_column(JSON)
    definition_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    experiment: Mapped[Experiment] = relationship(back_populates="versions")
    sessions: Mapped[list["ParticipantSession"]] = relationship(back_populates="version")


class ParticipantSession(Base):
    __tablename__ = "participant_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"), index=True)
    version_id: Mapped[str] = mapped_column(ForeignKey("experiment_versions.id"), index=True)
    participant_code: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    participant_token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    participant_token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    device_info: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    execution_plan_json: Mapped[list] = mapped_column(JSON, default=list)
    variables_json: Mapped[dict] = mapped_column(JSON, default=dict)
    condition_group: Mapped[str | None] = mapped_column(String(120), nullable=True)
    consent_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    consent_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timing_diagnostics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    experiment: Mapped[Experiment] = relationship(back_populates="sessions")
    version: Mapped[ExperimentVersion] = relationship(back_populates="sessions")
    responses: Mapped[list["TrialResponse"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class TrialResponse(Base):
    __tablename__ = "trial_responses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(ForeignKey("participant_sessions.id", ondelete="CASCADE"), index=True)
    trial_index: Mapped[int] = mapped_column(Integer, index=True)
    block_id: Mapped[str] = mapped_column(String(180))
    client_event_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    response_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    reaction_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    client_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    client_event_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    client_duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    stimulus_onset_perf_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    response_perf_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    timing_error_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    server_received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    session: Mapped[ParticipantSession] = relationship(back_populates="responses")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    resource_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
