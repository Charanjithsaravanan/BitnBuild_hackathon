from datetime import datetime, timezone
import csv
import io
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from .audit import audit
from .db import get_db
from .deps import get_current_user, get_request_context
from .experiment_engine import definition_hash
from .models import AuditEvent, Experiment, ExperimentVersion, ParticipantSession, TrialResponse, User
from .rate_limit import enforce_rate_limit
from .schemas import DraftUpdate, ExperimentCreate, ExperimentOut, ExperimentUpdate, PublishOut, VersionOut

router = APIRouter(prefix="/experiments", tags=["Researcher Experiments"])


def owned_experiment(db: Session, user_id: str, experiment_id: str) -> Experiment:
    experiment = db.scalar(select(Experiment).where(Experiment.id == experiment_id, Experiment.owner_id == user_id))
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return experiment


def slugify(name: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in name).strip("-")
    return "-".join(x for x in cleaned.split("-") if x)[:110] or "experiment"


def unique_slug(db: Session, base: str) -> str:
    candidate = base
    counter = 2
    while db.scalar(select(Experiment.id).where(Experiment.slug == candidate)):
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate[:120]


@router.post("", response_model=ExperimentOut, status_code=201)
def create_experiment(payload: ExperimentCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    base_slug = payload.slug or slugify(payload.name)
    slug = unique_slug(db, base_slug)
    definition = payload.definition.model_dump(mode="json")
    experiment = Experiment(owner_id=user.id, slug=slug, name=payload.name, description=payload.description, status="draft")
    version = ExperimentVersion(experiment=experiment, version=1, definition=definition, definition_hash=definition_hash(definition))
    db.add_all([experiment, version])
    db.flush()
    audit(db, user=user, action="experiment.create", resource_type="experiment", resource_id=experiment.id, context=get_request_context(request))
    db.commit()
    db.refresh(experiment)
    return experiment


@router.get("", response_model=list[ExperimentOut])
def list_experiments(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.scalars(select(Experiment).where(Experiment.owner_id == user.id).order_by(Experiment.created_at.desc())).all()


@router.get("/{experiment_id}", response_model=ExperimentOut)
def get_experiment(experiment_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return owned_experiment(db, user.id, experiment_id)


@router.patch("/{experiment_id}", response_model=ExperimentOut)
def update_experiment(experiment_id: str, payload: ExperimentUpdate, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    experiment = owned_experiment(db, user.id, experiment_id)
    if experiment.status == "archived":
        raise HTTPException(status_code=409, detail="Archived experiments cannot be edited")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(experiment, key, value)
    audit(db, user=user, action="experiment.update", resource_type="experiment", resource_id=experiment.id, context=get_request_context(request))
    db.commit()
    db.refresh(experiment)
    return experiment


@router.put("/{experiment_id}/draft", response_model=VersionOut)
def update_draft(experiment_id: str, payload: DraftUpdate, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    experiment = owned_experiment(db, user.id, experiment_id)
    if experiment.status == "archived":
        raise HTTPException(status_code=409, detail="Archived experiments cannot be edited")
    latest_version = db.scalar(select(func.max(ExperimentVersion.version)).where(ExperimentVersion.experiment_id == experiment.id)) or 0
    next_version = latest_version + 1
    definition = payload.definition.model_dump(mode="json")
    version = ExperimentVersion(experiment_id=experiment.id, version=next_version, definition=definition, definition_hash=definition_hash(definition))
    db.add(version)
    if experiment.status == "published":
        experiment.status = "draft"
    audit(db, user=user, action="experiment.draft_saved", resource_type="experiment", resource_id=experiment.id, context=get_request_context(request))
    db.commit()
    db.refresh(version)
    return version


@router.get("/{experiment_id}/versions", response_model=list[VersionOut])
def list_versions(experiment_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    experiment = owned_experiment(db, user.id, experiment_id)
    return db.scalars(select(ExperimentVersion).where(ExperimentVersion.experiment_id == experiment.id).order_by(ExperimentVersion.version.desc())).all()


@router.post("/{experiment_id}/publish", response_model=PublishOut)
def publish_experiment(experiment_id: str, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    experiment = owned_experiment(db, user.id, experiment_id)
    if experiment.status == "archived":
        raise HTTPException(status_code=409, detail="Archived experiments cannot be published")
    latest = db.scalar(select(ExperimentVersion).where(ExperimentVersion.experiment_id == experiment.id).order_by(ExperimentVersion.version.desc()))
    if not latest:
        raise HTTPException(status_code=400, detail="Experiment has no definition")
    experiment.status = "published"
    experiment.published_version = latest.version
    experiment.published_at = datetime.now(timezone.utc)
    audit(db, user=user, action="experiment.publish", resource_type="experiment", resource_id=experiment.id, context=get_request_context(request))
    db.commit()
    db.refresh(experiment)
    return {"experiment": experiment, "version": latest}


@router.post("/{experiment_id}/archive", response_model=ExperimentOut)
def archive_experiment(experiment_id: str, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    experiment = owned_experiment(db, user.id, experiment_id)
    experiment.status = "archived"
    audit(db, user=user, action="experiment.archive", resource_type="experiment", resource_id=experiment.id, context=get_request_context(request))
    db.commit()
    db.refresh(experiment)
    return experiment


@router.get("/{experiment_id}/audit")
def audit_log(experiment_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    experiment = owned_experiment(db, user.id, experiment_id)
    rows = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.resource_type == "experiment", AuditEvent.resource_id == experiment.id)
        .order_by(AuditEvent.created_at.desc())
        .limit(250)
    ).all()
    return {
        "events": [
            {
                "id": row.id, "action": row.action, "resource_type": row.resource_type,
                "resource_id": row.resource_id, "ip_address": row.ip_address,
                "created_at": row.created_at.isoformat(), "metadata": row.metadata_json,
            }
            for row in rows
        ]
    }


@router.get("/{experiment_id}/results.json")
def export_json(experiment_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    experiment = owned_experiment(db, user.id, experiment_id)
    sessions = db.scalars(select(ParticipantSession).where(ParticipantSession.experiment_id == experiment.id).order_by(ParticipantSession.started_at)).all()
    payload = []
    for session in sessions:
        responses = db.scalars(select(TrialResponse).where(TrialResponse.session_id == session.id).order_by(TrialResponse.trial_index)).all()
        payload.append({
            "session": {
                "id": session.id,
                "participant_code": session.participant_code,
                "status": session.status,
                "started_at": session.started_at.isoformat(),
                "completed_at": session.completed_at.isoformat() if session.completed_at else None,
                "device_info": session.device_info,
                "metadata": session.metadata_json,
                "version": session.version.version,
                "condition_group": session.condition_group,
                "consent_version": session.consent_version,
                "consent_accepted_at": session.consent_accepted_at.isoformat() if session.consent_accepted_at else None,
                "timing_diagnostics": session.timing_diagnostics_json,
            },
            "responses": [
                {
                    "id": r.id,
                    "trial_index": r.trial_index,
                    "block_id": r.block_id,
                    "response_value": r.response_value,
                    "correct": r.correct,
                    "reaction_time_ms": r.reaction_time_ms,
                    "client_started_at": r.client_started_at.isoformat() if r.client_started_at else None,
                    "client_event_time_ms": r.client_event_time_ms,
                    "client_duration_ms": r.client_duration_ms,
                    "stimulus_onset_perf_ms": r.stimulus_onset_perf_ms,
                    "response_perf_ms": r.response_perf_ms,
                    "timing_error_ms": r.timing_error_ms,
                    "server_received_at": r.server_received_at.isoformat(),
                    "metadata": r.metadata_json,
                }
                for r in responses
            ],
        })
    version = db.scalar(select(ExperimentVersion).where(ExperimentVersion.experiment_id == experiment.id, ExperimentVersion.version == experiment.published_version))
    return {
        "experiment": {"id": experiment.id, "name": experiment.name, "slug": experiment.slug, "published_version": experiment.published_version, "definition_hash": version.definition_hash if version else None},
        "sessions": payload,
    }


@router.get("/{experiment_id}/results.csv")
def export_csv(experiment_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    experiment = owned_experiment(db, user.id, experiment_id)
    rows = db.execute(
        select(ParticipantSession, TrialResponse, ExperimentVersion.version)
        .join(TrialResponse, TrialResponse.session_id == ParticipantSession.id)
        .join(ExperimentVersion, ExperimentVersion.id == ParticipantSession.version_id)
        .where(ParticipantSession.experiment_id == experiment.id)
        .order_by(ParticipantSession.started_at, TrialResponse.trial_index)
    ).all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "session_id", "participant_code", "version", "condition_group", "session_status", "started_at", "completed_at",
        "trial_index", "block_id", "response_value", "correct", "reaction_time_ms", "stimulus_onset_perf_ms",
        "response_perf_ms", "timing_error_ms", "client_started_at", "client_event_time_ms", "client_duration_ms", "server_received_at"
    ])
    for session, response, version in rows:
        writer.writerow([
            session.id, session.participant_code, version, session.condition_group, session.status,
            session.started_at.isoformat(), session.completed_at.isoformat() if session.completed_at else "",
            response.trial_index, response.block_id, response.response_value, response.correct, response.reaction_time_ms,
            response.stimulus_onset_perf_ms, response.response_perf_ms, response.timing_error_ms,
            response.client_started_at.isoformat() if response.client_started_at else "",
            response.client_event_time_ms, response.client_duration_ms, response.server_received_at.isoformat()
        ])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{experiment.slug}-results.csv"'},
    )
