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
CLAIM_ATTEMPTS = 3  # tries to claim a ticket before giving up when other workers win the race
DEFAULT_PRIORITY = 50
HIGH_PRIORITY = 80
LOW_PRIORITY = 20

# --- Scheduler ----------------------------------------------------------
DEFAULT_EVENT_SCAN_INTERVAL_MIN = 60
DEFAULT_WORKER_POLL_S = 3.0
WORKER_HEARTBEAT_KEY = "worker_heartbeat"
LAST_SCAN_KEY = "last_event_scan"
SCAN_REQUEST_KEY = "scan_requested"
HEARTBEAT_STALE_AFTER = timedelta(minutes=2)
MAX_EVENTS_PER_REVIEW = 10
MAX_NEWS_PER_STOCK = 10
REFRESH_INTERVALS: dict[str, timedelta] = {
    "technical_snapshot": timedelta(days=1),
    "valuation_score": timedelta(days=7),
    "thesis_check": timedelta(days=7),
    "sec_sync": timedelta(days=1),
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

# --- Documents / sources --------------------------------------------------
MAX_DOCUMENT_CHARS = 2_000_000
MAX_FETCH_BYTES = 8_000_000
MAX_REDIRECTS = 3
MAX_PDF_PAGES = 300
READ_CHUNK_CHARS = 6000
SEARCH_SNIPPET_CHARS = 240
MAX_SEARCH_HITS = 6
MIN_QUOTE_CHARS = 20
MAX_SECTIONS = 60
FETCH_MIN_INTERVAL_S = 0.2
FETCH_USER_AGENT = "WatchStreet/0.1 (+https://github.com/selopeylo/watchstreet)"
DOCUMENT_KINDS = ("filing", "gov", "press", "news", "dataset", "other")
PRIMARY_KINDS = ("filing", "gov", "press", "dataset")

# --- Intel ----------------------------------------------------------------
INTEL_CATEGORIES = (
    "company",
    "supply",
    "geopolitics",
    "macro",
    "regulatory",
    "commodity",
    "hazard",
)
INTEL_DIRECTIONS = ("bullish", "bearish", "neutral", "unknown")
SEVERITY_MIN = 1
SEVERITY_MAX = 5
SEVERITY_HIGH = 4
MAX_INTEL_PER_TICKET = 8
RELEVANCE_THRESHOLD = 2.0
MAX_DOCS_PER_TRIAGE = 10
MAX_QUERIES_PER_STOCK = 4
INGEST_MAX_ITEMS = 25
FEED_FAILURE_LIMIT = 5

# --- Geo / tripwires -------------------------------------------------------
EARTH_RADIUS_KM = 6371.0
QUAKE_MIN_MAGNITUDE = 5.0
QUAKE_RADIUS_KM = 300.0
COMMODITY_MOVE_PCT = 3.0
MAP_RECENT_DAYS = 14

# --- Graph ----------------------------------------------------------------
RELATION_KINDS = (
    "supplies",
    "buys_from",
    "owns",
    "operates",
    "located_in",
    "exposed_to",
    "competes",
    "depends_on",
)
ENTITY_KINDS = (
    "company",
    "supplier",
    "customer",
    "mine",
    "facility",
    "port",
    "country",
    "commodity",
)
MAX_GRAPH_NODES = 150
GRAPH_DEFAULT_DEPTH = 2
MAX_RELATIONS_PER_TICKET = 25
MAX_FILINGS_STORED = 6
SEC_FORMS_FULLTEXT = ("10-K", "20-F", "40-F", "10-Q", "6-K")
SEC_FORMS_ALERT = ("8-K", "6-K")
SCENARIO_SHOCKS = (-0.3, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3)
DEFAULT_RELATION_STRENGTH = 0.1  # used for exposure when a relation carries no share
COMMODITY_SYMBOL_KEY = "commodity_symbol"
