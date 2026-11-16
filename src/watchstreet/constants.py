"""Named constants. Anything numeric that carries meaning lives here, not inline."""

from datetime import timedelta

# --- Time ---------------------------------------------------------------
SECONDS_PER_HOUR = 3600
SECONDS_PER_DAY = 86_400

# --- Harness guardrails -------------------------------------------------
MAX_FOLLOWUPS_PER_TICKET = 4
DEDUPE_WINDOW = timedelta(hours=24)
MAX_TOOL_STEPS = 8
TOOL_RESULT_MAX_CHARS = 4000

# --- Valuation inputs, tickets ------------------------------------------
DEFAULT_DISCOUNT_RATE = 0.08
MAX_MINE_LIFE_YEARS = 30.0
STUCK_TICKET_TIMEOUT = timedelta(minutes=30)
STARTUP_LOCK_ID = 7_352_002  # serialises migration + seeding of web and worker starting together
MIGRATION_LOCK_ID = 7_352_001  # PostgreSQL advisory lock key serialising schema upgrades
CLAIM_ATTEMPTS = 3  # tries to claim a ticket before giving up when other workers win the race
DEFAULT_PRIORITY = 50

# --- Scheduler ----------------------------------------------------------
DEFAULT_EVENT_SCAN_INTERVAL_MIN = 60
DEFAULT_WORKER_POLL_S = 3.0
WORKER_HEARTBEAT_KEY = "worker_heartbeat"
LAST_SCAN_KEY = "last_event_scan"
SCAN_REQUEST_KEY = "scan_requested"
HEARTBEAT_STALE_AFTER = timedelta(minutes=2)
MAX_NEWS_PER_STOCK = 10

# --- Market data --------------------------------------------------------
QUOTE_CACHE_TTL_S = 900
CANDLE_CACHE_TTL_S = 900
HTTP_TIMEOUT_S = 15.0
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

# --- Units ---------------------------------------------------------------
PERCENT = 100.0

# --- UI -----------------------------------------------------------------
RECENT_LIMIT = 8
LIST_LIMIT = 200

# --- Documents / sources --------------------------------------------------
MAX_DOCUMENT_CHARS = 2_000_000
MAX_FETCH_BYTES = 8_000_000
MAX_REDIRECTS = 3
MAX_PDF_PAGES = 300
READ_CHUNK_CHARS = 6000
SEARCH_SNIPPET_CHARS = 240
MAX_SEARCH_HITS = 6
MIN_QUOTE_CHARS = 20
FETCH_MIN_INTERVAL_S = 0.2
FETCH_USER_AGENT = "WatchStreet/0.1 (+https://github.com/selopeylo/watchstreet)"

# --- Intel ----------------------------------------------------------------
SEVERITY_HIGH = 4
INGEST_MAX_ITEMS = 25

# --- Geo / tripwires -------------------------------------------------------
EARTH_RADIUS_KM = 6371.0
QUAKE_MIN_MAGNITUDE = 5.0
QUAKE_RADIUS_KM = 300.0
MAP_RECENT_DAYS = 14

# --- World explorer ---------------------------------------------------------
STALE_FACT_AFTER = timedelta(days=456)  # about 15 months: a yearly figure missed one cycle
NEIGHBOUR_RADIUS_KM = 60.0
MIN_PEER_GROUP = 3  # fewer comparable assets give no outlier test and no estimate
OUTLIER_MAD_FACTOR = 3.0
MAD_TO_SIGMA = 1.4826
LOWER_QUARTILE = 0.25
UPPER_QUARTILE = 0.75
MAX_OPEN_PROPOSALS_PER_SUBJECT = 6
MAX_SELECTION = 8
SESSION_TTL = timedelta(days=30)
MAX_LOGIN_FAILURES = 5  # then logins are refused for LOGIN_LOCK
LOGIN_LOCK = timedelta(minutes=5)
REGISTRY_MAX_RESULTS = 300  # per import; a larger area must be loaded in parts
REGISTRY_MAX_SPAN_DEG = 25.0  # largest box edge accepted for one import
DUPLICATE_RADIUS_KM = 2.0  # same name within this distance is the same mine
SENSITIVITY_FACTORS = (-0.5, -0.3, 0.0, 0.3, 0.5)  # price moves shown on the company card
SHORT_RUNWAY_MONTHS = 12.0  # below this a financing is likely before the next catalyst
CHANGES_LIMIT = 200
PRICE_HISTORY_INTERVAL = "1wk"
LAST_VISIT_KEY = "last_visit"
MAX_AGENT_FACTS = 20
MAX_CONTEXT_SNIPPETS = 8
DAYS_PER_YEAR = 365.25
# weights of the proposal value score; they sum to 1
VALUE_WEIGHTS: dict[str, float] = {
    "insight": 0.30,
    "relevance": 0.25,
    "novelty": 0.20,
    "data": 0.15,
    "investment": 0.10,
}

# analysis import
IMPORT_TOLERANCE = 0.05  # relative difference up to which two figures count as the same
MAX_LAT, MAX_LON = 90.0, 180.0
MIN_IMPORT_CHARS = 20
MIN_REASON_CHARS = 10  # a reason shorter than this is a formality, not a reason
USER_CONFIRMED = "user_confirmed"  # formula_key of an imported figure the user vouched for
MAX_IMPORT_ROWS = 2000
MAX_IMPORT_PROMPT_CHARS = 60_000

# Mineral-tenure registers: at most this many overlapping titles per click, texts cut to length.
MAX_CLAIMS_PER_POINT = 20
CLAIM_TEXT_CHARS = 160

# Macro series: history kept from this year on; each refresh re-reads the last days because
# statistical offices revise recent values.
MACRO_HISTORY_START_YEAR = 2003
MACRO_REVISION_DAYS = 400
MACRO_SYNC_KEY = "macro_synced"
MACRO_SPARK_POINTS = 60
MACRO_CHANGE_DAYS = 365

# Charts: a formula is short; an observation older than the gap is not used for another day;
# a matrix cell needs this many shared observations before it shows a change.
EXPRESSION_MAX_CHARS = 300
EXPRESSION_MAX_NODES = 80
SERIES_MAX_GAP_DAYS = 10
MATRIX_MIN_POINTS = 12
MATRIX_YEARS = 10
MATRIX_CELL_POINTS = 260
REGIME_DEFAULT_YEARS = 5
REGIME_MAX_POINTS = 400
LENS_NAME_CHARS = 80
