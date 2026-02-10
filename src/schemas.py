"""Pydantic schemas for API request/response models."""

from datetime import datetime

from pydantic import BaseModel


# ── Job Schemas ──────────────────────────────────────────────

class JobResponse(BaseModel):
    id: int
    title: str
    company: str
    location: str | None = None
    url: str
    source: str
    match_score: float
    status: str
    discovered_at: datetime

    model_config = {"from_attributes": True}


class JobListResponse(BaseModel):
    total: int
    jobs: list[JobResponse]


class JobUpdateRequest(BaseModel):
    status: str | None = None
    notes: str | None = None


# ── Analysis Schemas ─────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    resume_text: str
    job_description: str


class KeywordInfo(BaseModel):
    keyword: str
    category: str
    importance: str = "medium"


class AnalyzeResponse(BaseModel):
    overall_score: int
    breakdown: dict[str, int]
    missing_keywords: list[KeywordInfo]
    suggestions: list[str]
    formatting_issues: list[str]


# ── Profile Schemas ──────────────────────────────────────────

class ProfileUpdateRequest(BaseModel):
    section: str  # "skills" | "experience" | "education" | ...
    data: dict


# ── Application Schemas ──────────────────────────────────────

class ApplyRequest(BaseModel):
    job_ids: list[int]
    dry_run: bool = False


class ApplyResultItem(BaseModel):
    job_id: int
    status: str
    message: str


class ApplyResponse(BaseModel):
    results: list[ApplyResultItem]


# ── Pipeline Schemas ─────────────────────────────────────────

class PipelineStatusResponse(BaseModel):
    is_running: bool
    current_phase: str | None = None
    jobs_processed: int = 0
    jobs_applied: int = 0
    jobs_failed: int = 0
    started_at: datetime | None = None


# ── Resume Schemas ───────────────────────────────────────────

class ResumeResponse(BaseModel):
    id: int
    name: str | None = None
    target_job_id: int | None = None
    file_path: str | None = None
    ats_score: float | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ResumeGenerateRequest(BaseModel):
    job_id: int
    template: str = "classic"
