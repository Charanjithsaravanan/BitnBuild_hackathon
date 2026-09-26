from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .deps import get_participant_session
from .db import get_db
from .experiment_engine import build_step_lookup, choose_condition_group, compile_execution_plan, generate_seed
from .models import Experiment, ExperimentVersion, ParticipantSession, TrialResponse
from .rate_limit import enforce_rate_limit
from .schemas import BatchResponseCreate, CompleteOut, PublicExperimentOut, ResponseCreate, ResponseOut, SessionCreate, SessionCreatedOut, SessionOut, TimingDiagnostics
from .security import generate_participant_token, hash_participant_token

router = APIRouter(prefix="/public", tags=["Participant Runtime"])
settings = get_settings()


def public_experiment(db: Session, slug: str) -> tuple[Experiment, ExperimentVersion]:
    experiment = db.scalar(select(Experiment).where(Experiment.slug == slug, Experiment.status == "published"))
    if not experiment or not experiment.published_version:
        raise HTTPException(status_code=404, detail="Published experiment not found")
    version = db.scalar(select(ExperimentVersion).where(ExperimentVersion.experiment_id == experiment.id, ExperimentVersion.version == experiment.published_version))
    if not version:
        raise HTTPException(status_code=500, detail="Published experiment definition is unavailable")
    return experiment, version


def session_out(session: ParticipantSession) -> SessionOut:
    requires_consent = bool((session.version.definition.get("settings") or {}).get("consent_required", True)) and session.consent_accepted_at is None
    return SessionOut(
        id=session.id,
        experiment_id=session.experiment_id,
        version=session.version.version,
        status=session.status,
        started_at=session.started_at,
        completed_at=session.completed_at,
        requires_consent=requires_consent,
        condition_group=session.condition_group,
    )


@router.get("/experiments/{slug}", response_model=PublicExperimentOut)
def get_public_experiment(slug: str, db: Session = Depends(get_db)):
    experiment, version = public_experiment(db, slug)
    return PublicExperimentOut(
        id=experiment.id,
        slug=experiment.slug,
        name=experiment.name,
        description=experiment.description,
        version=version.version,
        definition=version.definition,
        definition_hash=version.definition_hash,
    )


@router.post("/experiments/{slug}/sessions", response_model=SessionCreatedOut, status_code=201)
def create_session(slug: str, payload: SessionCreate, request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(request, "public-session", settings.public_rate_limit_per_minute)
    experiment, version = public_experiment(db, slug)
    definition = version.definition
    study_settings = definition.get("settings") or {}
    required_consent = bool(study_settings.get("consent_required", True))
    consent_version = study_settings.get("consent_version", "1.0")
    if required_consent:
        if not payload.consent_accepted:
            raise HTTPException(status_code=403, detail="Consent is required before the study can begin")
        if payload.consent_version != consent_version:
            raise HTTPException(status_code=409, detail="Consent version is outdated")

    token = generate_participant_token()
    seed = generate_seed()
    plan = compile_execution_plan(definition, seed)
    condition_group = choose_condition_group(study_settings.get("counterbalance_groups") or [], seed)
    now = datetime.now(timezone.utc)
    session = ParticipantSession(
        experiment_id=experiment.id,
        version_id=version.id,
        participant_code=payload.participant_code,
        device_info=payload.device_info,
        metadata_json=payload.metadata,
        status="active",
        participant_token_hash=hash_participant_token(token),
        participant_token_expires_at=now + timedelta(hours=settings.participant_session_hours),
        execution_plan_json=plan,
        variables_json={**dict(definition.get("variables") or {}), "condition_group": condition_group},
        condition_group=condition_group,
        consent_version=consent_version if required_consent else None,
        consent_accepted_at=now if required_consent and payload.consent_accepted else None,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return SessionCreatedOut(
        **session_out(session).model_dump(),
        participant_token=token,
        participant_token_expires_at=session.participant_token_expires_at,
        execution_plan=plan,
        definition_hash=version.definition_hash,
        variables=session.variables_json,
    )


@router.get("/sessions/me", response_model=SessionOut)
def get_my_session(session: ParticipantSession = Depends(get_participant_session)):
    return session_out(session)


@router.post("/sessions/me/timing-diagnostics", response_model=SessionOut)
def save_timing_diagnostics(payload: TimingDiagnostics, request: Request, db: Session = Depends(get_db), session: ParticipantSession = Depends(get_participant_session)):
    enforce_rate_limit(request, "public-timing", settings.public_rate_limit_per_minute)
    session.timing_diagnostics_json = payload.model_dump(mode="json")
    db.commit()
    db.refresh(session)
    return session_out(session)


def _build_response(session: ParticipantSession, payload: ResponseCreate, db: Session) -> TrialResponse:
    if session.consent_accepted_at is None and (session.version.definition.get("settings") or {}).get("consent_required", True):
        raise HTTPException(status_code=403, detail="Consent has not been recorded")

    if payload.trial_index >= len(session.execution_plan_json):
        raise HTTPException(status_code=400, detail="Trial index is outside the session execution plan")
    step = session.execution_plan_json[payload.trial_index]
    expected_block_ids = set()
    if step.get("kind") == "block":
        expected_block_ids.add(step["block_id"])
    elif step.get("kind") == "trial":
        expected_block_ids.add(f"{step['group_id']}::{step['trial_id']}::{step['repetition']}")
        expected_block_ids.add(step["group_id"])
    if payload.block_id not in expected_block_ids:
        raise HTTPException(status_code=400, detail="block_id does not match the session execution plan")

    existing_trial = db.scalar(select(TrialResponse).where(TrialResponse.session_id == session.id, TrialResponse.trial_index == payload.trial_index))
    if existing_trial:
        raise HTTPException(status_code=409, detail=f"Trial {payload.trial_index} already has a response")

    existing_event = db.scalar(select(TrialResponse).where(TrialResponse.session_id == session.id, TrialResponse.client_event_id == payload.client_event_id))
    if existing_event:
        raise HTTPException(status_code=409, detail="client_event_id already exists")

    return TrialResponse(
        session_id=session.id,
        trial_index=payload.trial_index,
        block_id=payload.block_id,
        client_event_id=payload.client_event_id,
        response_value=payload.response_value,
        correct=payload.correct,
        reaction_time_ms=payload.reaction_time_ms if payload.reaction_time_ms is not None else payload.client_duration_ms,
        client_started_at=payload.client_started_at,
        client_event_time_ms=payload.client_event_time_ms,
        client_duration_ms=payload.client_duration_ms,
        stimulus_onset_perf_ms=payload.stimulus_onset_perf_ms,
        response_perf_ms=payload.response_perf_ms,
        timing_error_ms=payload.timing_error_ms,
        metadata_json=payload.metadata,
    )


@router.post("/sessions/me/responses", response_model=ResponseOut, status_code=201)
def record_response(payload: ResponseCreate, request: Request, db: Session = Depends(get_db), session: ParticipantSession = Depends(get_participant_session)):
    enforce_rate_limit(request, "public-response", settings.public_rate_limit_per_minute)
    if session.status != "active":
        raise HTTPException(status_code=409, detail="Session is not active")
    response = _build_response(session, payload, db)
    db.add(response)
    db.commit()
    db.refresh(response)
    return response


@router.post("/sessions/me/responses/batch", response_model=list[ResponseOut], status_code=201)
def record_response_batch(payload: BatchResponseCreate, request: Request, db: Session = Depends(get_db), session: ParticipantSession = Depends(get_participant_session)):
    enforce_rate_limit(request, "public-response-batch", settings.public_rate_limit_per_minute)
    if session.status != "active":
        raise HTTPException(status_code=409, detail="Session is not active")
    responses = [_build_response(session, item, db) for item in payload.responses]
    db.add_all(responses)
    db.commit()
    for response in responses:
        db.refresh(response)
    return responses


@router.post("/sessions/me/complete", response_model=CompleteOut)
def complete_session(request: Request, db: Session = Depends(get_db), session: ParticipantSession = Depends(get_participant_session)):
    enforce_rate_limit(request, "public-complete", settings.public_rate_limit_per_minute)
    if session.status == "completed":
        count = len(session.responses)
        return CompleteOut(session=session_out(session), response_count=count, debrief_text=(session.version.definition.get("settings") or {}).get("debrief_text", "Thank you for participating."))
    if session.status != "active":
        raise HTTPException(status_code=409, detail="Session cannot be completed")
    session.status = "completed"
    session.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(session)
    return CompleteOut(
        session=session_out(session),
        response_count=len(session.responses),
        debrief_text=(session.version.definition.get("settings") or {}).get("debrief_text", "Thank you for participating."),
    )
