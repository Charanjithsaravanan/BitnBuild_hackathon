from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: EmailStr
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class BlockType(str, Enum):
    instruction = "instruction"
    consent = "consent"
    fixation = "fixation"
    stimulus = "stimulus"
    response = "response"
    delay = "delay"
    trial_group = "trial_group"
    branch = "branch"
    set_variable = "set_variable"


class Stimulus(BaseModel):
    kind: str = Field(pattern=r"^(text|image|audio|video|html|color)$")
    value: str
    alt: str | None = None


class TrialDefinition(BaseModel):
    id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_-]+$")
    stimulus: Stimulus | None = None
    text: str | None = None
    duration_ms: int | None = Field(default=None, ge=0, le=3_600_000)
    response_mode: str = Field(default="keyboard", pattern=r"^(keyboard|button|none)$")
    expected_response: str | None = Field(default=None, max_length=200)
    allowed_responses: list[str] | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class ExperimentBlock(BaseModel):
    id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_-]+$")
    type: BlockType
    text: str | None = None
    stimulus: Stimulus | None = None
    duration_ms: int | None = Field(default=None, ge=0, le=3_600_000)
    expected_response: str | None = Field(default=None, max_length=200)
    allowed_responses: list[str] | None = None
    data: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_type_data(self):
        if self.type == BlockType.trial_group:
            trials = self.data.get("trials")
            if not isinstance(trials, list) or not trials:
                raise ValueError("trial_group.data.trials must be a non-empty list")
            self.data["repetitions"] = max(1, min(int(self.data.get("repetitions", 1)), 1000))
            self.data["randomize"] = bool(self.data.get("randomize", False))
        elif self.type == BlockType.branch:
            condition = self.data.get("condition")
            true_target = self.data.get("true_target")
            false_target = self.data.get("false_target")
            if not isinstance(condition, str) or not condition.strip():
                raise ValueError("branch.data.condition is required")
            if not isinstance(true_target, str) or not isinstance(false_target, str):
                raise ValueError("branch.data.true_target and false_target are required")
        elif self.type == BlockType.set_variable:
            name = self.data.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("set_variable.data.name is required")
            if self.data.get("operation", "set") not in {"set", "increment", "decrement"}:
                raise ValueError("set_variable.data.operation must be set, increment, or decrement")
        return self


class ExperimentSettings(BaseModel):
    fullscreen: bool = False
    randomize_trials: bool = False
    collect_device_info: bool = True
    prevent_back_navigation: bool = True
    timing_diagnostics: bool = True
    consent_required: bool = True
    consent_version: str = Field(default="1.0", max_length=80)
    consent_text: str = Field(default="I have read the study information and agree to participate.", max_length=20000)
    debrief_text: str = Field(default="Thank you for participating.", max_length=20000)
    counterbalance_groups: list[str] = Field(default_factory=list, max_length=32)
    session_resume: bool = True


class ExperimentDefinition(BaseModel):
    settings: ExperimentSettings = Field(default_factory=ExperimentSettings)
    variables: dict[str, int | float | str | bool | None] = Field(default_factory=dict)
    blocks: list[ExperimentBlock] = Field(min_length=1, max_length=5000)

    @field_validator("blocks")
    @classmethod
    def unique_block_ids(cls, blocks):
        ids = [b.id for b in blocks]
        if len(ids) != len(set(ids)):
            raise ValueError("block ids must be unique")
        return blocks

    @model_validator(mode="after")
    def validate_references(self):
        ids = {b.id for b in self.blocks}
        for block in self.blocks:
            if block.type == BlockType.branch:
                if block.data["true_target"] not in ids or block.data["false_target"] not in ids:
                    raise ValueError(f"Branch {block.id} references an unknown target")
        return self


class ExperimentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    slug: str | None = Field(default=None, min_length=3, max_length=120, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    definition: ExperimentDefinition


class ExperimentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)


class DraftUpdate(BaseModel):
    definition: ExperimentDefinition


class ExperimentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    slug: str
    name: str
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None
    published_version: int | None


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    version: int
    definition: dict
    definition_hash: str
    created_at: datetime


class PublishOut(BaseModel):
    experiment: ExperimentOut
    version: VersionOut


class PublicExperimentOut(BaseModel):
    id: str
    slug: str
    name: str
    description: str | None
    version: int
    definition: dict
    definition_hash: str


class SessionCreate(BaseModel):
    participant_code: str | None = Field(default=None, max_length=120)
    device_info: dict | None = None
    metadata: dict | None = None
    consent_accepted: bool = False
    consent_version: str | None = Field(default=None, max_length=80)


class SessionOut(BaseModel):
    id: str
    experiment_id: str
    version: int
    status: str
    started_at: datetime
    completed_at: datetime | None
    requires_consent: bool
    condition_group: str | None = None


class SessionCreatedOut(SessionOut):
    participant_token: str
    participant_token_expires_at: datetime
    execution_plan: list[dict]
    definition_hash: str
    variables: dict = Field(default_factory=dict)


class ResponseCreate(BaseModel):
    client_event_id: str = Field(min_length=8, max_length=100)
    trial_index: int = Field(ge=0, le=1_000_000)
    block_id: str = Field(min_length=1, max_length=180)
    response_value: str | None = Field(default=None, max_length=5000)
    correct: bool | None = None
    reaction_time_ms: float | None = Field(default=None, ge=0, le=3_600_000)
    client_started_at: datetime | None = None
    client_event_time_ms: float | None = Field(default=None, ge=0)
    client_duration_ms: float | None = Field(default=None, ge=0, le=3_600_000)
    stimulus_onset_perf_ms: float | None = Field(default=None, ge=0)
    response_perf_ms: float | None = Field(default=None, ge=0)
    timing_error_ms: float | None = Field(default=None, ge=0, le=3_600_000)
    metadata: dict | None = None


class ResponseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    trial_index: int
    block_id: str
    response_value: str | None
    correct: bool | None
    reaction_time_ms: float | None
    client_started_at: datetime | None
    client_event_time_ms: float | None
    client_duration_ms: float | None
    stimulus_onset_perf_ms: float | None
    response_perf_ms: float | None
    timing_error_ms: float | None
    client_event_id: str
    server_received_at: datetime


class BatchResponseCreate(BaseModel):
    responses: list[ResponseCreate] = Field(min_length=1, max_length=500)


class TimingDiagnostics(BaseModel):
    performance_now_resolution_ms: float = Field(ge=0, le=1000)
    refresh_rate_hz: float | None = Field(default=None, ge=1, le=1000)
    refresh_interval_ms: float | None = Field(default=None, ge=0, le=1000)
    refresh_jitter_ms: float | None = Field(default=None, ge=0, le=1000)
    calibration_samples: int = Field(ge=1, le=5000)
    visibility_changes: int = Field(default=0, ge=0, le=100000)
    timer_early_fire_ms: float | None = Field(default=None, ge=0, le=1000)
    browser: str | None = Field(default=None, max_length=200)
    platform: str | None = Field(default=None, max_length=200)
    diagnostics_version: str = "1.0"


class ConsentRecord(BaseModel):
    accepted: bool
    version: str = Field(min_length=1, max_length=80)


class CompleteOut(BaseModel):
    session: SessionOut
    response_count: int
    debrief_text: str
