"""Initial LabForge research platform schema."""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "experiments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("owner_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_version", sa.Integer(), nullable=True),
    )
    op.create_index("ix_experiments_owner_id", "experiments", ["owner_id"])
    op.create_index("ix_experiments_slug", "experiments", ["slug"], unique=True)
    op.create_index("ix_experiments_status", "experiments", ["status"])

    op.create_table(
        "experiment_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("experiment_id", sa.String(length=36), sa.ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("definition_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("experiment_id", "version", name="uq_experiment_version"),
    )
    op.create_index("ix_experiment_versions_experiment_id", "experiment_versions", ["experiment_id"])
    op.create_index("ix_experiment_versions_definition_hash", "experiment_versions", ["definition_hash"])

    op.create_table(
        "participant_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("experiment_id", sa.String(length=36), sa.ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_id", sa.String(length=36), sa.ForeignKey("experiment_versions.id"), nullable=False),
        sa.Column("participant_code", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("participant_token_hash", sa.String(length=64), nullable=False),
        sa.Column("participant_token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("device_info", sa.JSON(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("execution_plan_json", sa.JSON(), nullable=False),
        sa.Column("variables_json", sa.JSON(), nullable=False),
        sa.Column("condition_group", sa.String(length=120), nullable=True),
        sa.Column("consent_version", sa.String(length=80), nullable=True),
        sa.Column("consent_accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timing_diagnostics_json", sa.JSON(), nullable=True),
    )
    op.create_index("ix_participant_sessions_experiment_id", "participant_sessions", ["experiment_id"])
    op.create_index("ix_participant_sessions_version_id", "participant_sessions", ["version_id"])
    op.create_index("ix_participant_sessions_participant_code", "participant_sessions", ["participant_code"])
    op.create_index("ix_participant_sessions_status", "participant_sessions", ["status"])
    op.create_index("ix_participant_sessions_participant_token_hash", "participant_sessions", ["participant_token_hash"], unique=True)
    op.create_index("ix_participant_sessions_participant_token_expires_at", "participant_sessions", ["participant_token_expires_at"])

    op.create_table(
        "trial_responses",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("participant_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("trial_index", sa.Integer(), nullable=False),
        sa.Column("block_id", sa.String(length=180), nullable=False),
        sa.Column("client_event_id", sa.String(length=100), nullable=False),
        sa.Column("response_value", sa.Text(), nullable=True),
        sa.Column("correct", sa.Boolean(), nullable=True),
        sa.Column("reaction_time_ms", sa.Float(), nullable=True),
        sa.Column("client_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("client_event_time_ms", sa.Float(), nullable=True),
        sa.Column("client_duration_ms", sa.Float(), nullable=True),
        sa.Column("stimulus_onset_perf_ms", sa.Float(), nullable=True),
        sa.Column("response_perf_ms", sa.Float(), nullable=True),
        sa.Column("timing_error_ms", sa.Float(), nullable=True),
        sa.Column("server_received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
    )
    op.create_index("ix_trial_responses_session_id", "trial_responses", ["session_id"])
    op.create_index("ix_trial_responses_trial_index", "trial_responses", ["trial_index"])
    op.create_index("ix_trial_responses_client_event_id", "trial_responses", ["client_event_id"])
    op.create_index("ix_trial_responses_server_received_at", "trial_responses", ["server_received_at"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("resource_type", sa.String(length=80), nullable=True),
        sa.Column("resource_id", sa.String(length=120), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=1000), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_events_user_id", "audit_events", ["user_id"])
    op.create_index("ix_audit_events_action", "audit_events", ["action"])
    op.create_index("ix_audit_events_resource_id", "audit_events", ["resource_id"])
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])


def downgrade():
    op.drop_table("audit_events")
    op.drop_table("trial_responses")
    op.drop_table("participant_sessions")
    op.drop_table("experiment_versions")
    op.drop_table("experiments")
    op.drop_table("users")
