"""Domain vocabulary shared by models, workflows and the UI."""

from enum import StrEnum


class TicketStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


OPEN_STATUSES = (TicketStatus.QUEUED, TicketStatus.RUNNING)


class TicketOrigin(StrEnum):
    USER = "user"
    INTAKE = "intake"
    FOLLOWUP = "followup"
    EVENT = "event"
    SCHEDULE = "schedule"


class WorkflowKey(StrEnum):
    INITIAL_HOLDING = "initial_holding"
    INITIAL_WATCH = "initial_watch"
    TOPIC_ANALYSIS = "topic_analysis"
    EVENT_REVIEW = "event_review"
    THESIS_CHECK = "thesis_check"
    VALUATION_SCORE = "valuation_score"
    TECHNICAL_SNAPSHOT = "technical_snapshot"
    CLASSIFY_STOCK = "classify_stock"
    RESEARCH_DATAPOINTS = "research_datapoints"
    BRIEFING = "briefing"
    SEC_SYNC = "sec_sync"
    READ_FILING = "read_filing"
    INTEL_TRIAGE = "intel_triage"


class InsightCategory(StrEnum):
    GOAL = "goal"
    RISK = "risk"
    CATALYST = "catalyst"
    VALUATION = "valuation"
    TECHNICAL = "technical"
    ACTION = "action"
    NOTE = "note"


class ThesisStatus(StrEnum):
    ACTIVE = "active"
    CONFIRMED = "confirmed"
    WEAKENED = "weakened"
    INVALIDATED = "invalidated"


class ProfileSource(StrEnum):
    """Who chose a stock's valuation profile; a later entry outranks the earlier ones."""

    NONE = "none"
    AUTO = "auto"
    AGENT = "agent"
    USER = "user"


class DataOrigin(StrEnum):
    """Who wrote a datapoint, relation or entity; user entries are never overwritten."""

    USER = "user"
    AGENT = "agent"
