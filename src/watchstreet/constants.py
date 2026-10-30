"""Named constants. Anything numeric that carries meaning lives here, not inline."""

from datetime import timedelta

# --- Time ---------------------------------------------------------------
SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 3600
SECONDS_PER_DAY = 86_400

# --- Harness guardrails -------------------------------------------------
MAX_FOLLOWUP_DEPTH = 2
MAX_OPEN_TICKETS_PER_STOCK = 8
MAX_FOLLOWUPS_PER_TICKET = 4
DEDUPE_WINDOW = timedelta(hours=24)
MAX_LLM_ATTEMPTS = 2
MAX_TOOL_STEPS = 8
TOOL_RESULT_MAX_CHARS = 4000
PRICE_SUMMARY_TAIL_BARS = 12
DEFAULT_NEWS_LIMIT = 5
THESIS_PREVIEW_CHARS = 240
SCORE_HISTORY_LIMIT = 5
MAX_INSIGHTS_PER_TICKET = 10
MAX_DATAPOINTS_PER_TICKET = 30
BRIEFING_PRIORITY = 10
MAX_BRIEFING_BULLETS = 4

# --- Profiles / valuation inputs ----------------------------------------
DEFAULT_PROFILE = "generic"
DEFAULT_DISCOUNT_RATE = 0.08
MAX_MINE_LIFE_YEARS = 30.0
DEFAULT_OWNERSHIP = 1.0
DEFAULT_REPORTING_CURRENCY = "USD"
PROVISIONAL_NOTE = "vorläufig"
STUCK_TICKET_TIMEOUT = timedelta(minutes=30)
DEFAULT_PRIORITY = 50
HIGH_PRIORITY = 80
LOW_PRIORITY = 20

# --- Scheduler ----------------------------------------------------------
DEFAULT_EVENT_SCAN_INTERVAL_MIN = 60
DEFAULT_WORKER_POLL_S = 3.0
WORKER_HEARTBEAT_KEY = "worker_heartbeat"
LAST_SCAN_KEY = "last_event_scan"
HEARTBEAT_STALE_AFTER = timedelta(minutes=2)
MAX_EVENTS_PER_REVIEW = 10
MAX_NEWS_PER_STOCK = 10
REFRESH_INTERVALS: dict[str, timedelta] = {
    "technical_snapshot": timedelta(days=1),
    "valuation_score": timedelta(days=7),
    "thesis_check": timedelta(days=7),
}

# --- Market data --------------------------------------------------------
QUOTE_CACHE_TTL_S = 900
CANDLE_CACHE_TTL_S = 900
HTTP_TIMEOUT_S = 15.0
DEFAULT_INTERVAL = "1h"
# interval -> (range requested from provider, bars per day used by demo data)
INTERVAL_RANGES: dict[str, str] = {"1h": "1mo", "1d": "1y", "1wk": "5y"}
INTERVAL_SECONDS: dict[str, int] = {
    "1h": SECONDS_PER_HOUR,
    "1d": SECONDS_PER_DAY,
    "1wk": 7 * SECONDS_PER_DAY,
}
DEMO_CANDLE_COUNT = 160
DEMO_BASE_PRICE_MIN = 20.0
DEMO_BASE_PRICE_SPAN = 280.0
DEMO_VOLATILITY = 0.012
DEMO_DRIFT = 0.0004
DEMO_VOLUME_BASE = 500_000

# --- Indicators ---------------------------------------------------------
SMA_FAST = 20
SMA_SLOW = 50
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70.0
RSI_OVERSOLD = 30.0
MOMENTUM_BARS = 20
PERCENT = 100.0

# --- Scoring ------------------------------------------------------------
SCORE_MIN = 0.0
SCORE_MAX = 100.0
SCORE_NEUTRAL = 50.0
SCORE_GOOD = 66.0
SCORE_BAD = 40.0
SCORE_DROP_WEAKENS_THESIS = 15.0
MIN_CRITERIA_FOR_SCORE = 3
VALUATION_SCHEME = "valuation_v1"
TECHNICAL_SCHEME = "technical_v1"
CHANGE_PERIOD_BARS_DAY = 24

# --- UI -----------------------------------------------------------------
TIMELINE_LIMIT = 60
OPEN_PANELS = 2
RECENT_LIMIT = 8
LIST_LIMIT = 200
TEXT_PREVIEW_CHARS = 180
