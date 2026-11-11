"""Domain vocabulary shared by models, services and the API."""

from enum import StrEnum


class TicketStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


OPEN_STATUSES = (TicketStatus.QUEUED, TicketStatus.RUNNING)


class WorkflowKey(StrEnum):
    FILL_METRIC = "fill_metric"
    ESTIMATE_COST = "estimate_cost"
    STRATEGIC_QUESTION = "strategic_question"
    READ_DOCUMENT = "read_document"


class SubjectType(StrEnum):
    """What a fact, ticket, finding or thesis link can hang off."""

    ASSET = "asset"
    COMPANY = "company"
    COMMODITY = "commodity"
    THESIS = "thesis"


class AssetKind(StrEnum):
    MINE = "mine"
    PROJECT = "project"
    DEPOSIT = "deposit"


class AssetStatus(StrEnum):
    EXPLORATION = "exploration"
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    CARE = "care_maintenance"
    CLOSED = "closed"


class StakeRole(StrEnum):
    OPERATOR = "operator"
    OWNER = "owner"
    ROYALTY = "royalty"
    STREAM = "stream"
    JV_PARTNER = "jv_partner"


class Provenance(StrEnum):
    """How a number came about. ``UNKNOWN`` is never stored; it is the absence of a fact."""

    REPORTED = "reported"
    DERIVED = "derived"
    ESTIMATED = "estimated"
    UNKNOWN = "unknown"


class ClaimKind(StrEnum):
    """What a number claims."""

    ACTUAL = "actual"
    GUIDANCE = "guidance"
    HYPOTHESIS = "hypothesis"
    AI_INFERENCE = "ai_inference"


class DataOrigin(StrEnum):
    """Who wrote a fact; user entries are never overwritten by the others."""

    USER = "user"
    AGENT = "agent"
    API = "api"
    ENGINE = "engine"


class View(StrEnum):
    """Which information counts for a reference date."""

    AS_KNOWN = "as_known"  # only what had been published by then
    HINDSIGHT = "hindsight"  # everything about the period, whenever it was published


class ProposalState(StrEnum):
    DRAFT = "draft"
    DISMISSED = "dismissed"
    STARTED = "started"


class FindingKind(StrEnum):
    ANSWER = "answer"
    ANOMALY = "anomaly"
    PATTERN = "pattern"


class Epistemic(StrEnum):
    """Strength of a claimed relationship; only sourced agent research may raise it."""

    CORRELATION = "correlation"
    HYPOTHESIS = "hypothesis"
    EVIDENCED = "evidenced"


class KnowledgeStatus(StrEnum):
    UNEXAMINED = "unexamined"
    KNOWN = "known"
    DEEP = "deep"
    NEW = "new"
    STALE = "stale"


class Stance(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    CONTEXT = "context"


class ThesisStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"
