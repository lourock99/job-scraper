import os
from dotenv import load_dotenv

load_dotenv()

# --- DO NOT MODIFY THE BELOW SECTION ---

# =================================================================
# 1. CORE SYSTEM CONFIGURATION (Do Not Modify)
# =================================================================
SUPABASE_URL: str = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY: str = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_TABLE_NAME: str = "jobs"
SUPABASE_CUSTOMIZED_RESUMES_TABLE_NAME = "customized_resumes"
SUPABASE_STORAGE_BUCKET="personalized_resumes"
SUPABASE_RESUME_STORAGE_BUCKET="resumes"
SUPABASE_BASE_RESUME_TABLE_NAME = "base_resume"
BASE_RESUME_PATH = "resume.json"

# API keys — set only the key(s) needed for your chosen provider.
LLM_API_KEY = os.environ.get("LLM_API_KEY") or os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMINI_FIRST_API_KEY")
JSEARCH_API_KEY = os.environ.get("JSEARCH_API_KEY")

# =================================================================
# 2. USER PREFERENCES (Editable)
# =================================================================

# --- LLM Settings ---
# Use any model supported by LiteLLM (gemini, openai/gpt-4o-mini, groq/llama-3.3-70b-versatile)
# Full list of supported models & naming: https://docs.litellm.ai/docs/providers
LLM_MODEL = "anthropic/claude-sonnet-4-5"

# --- Search Configuration ---
LINKEDIN_SEARCH_QUERIES = [
    "Software License Compliance",
    "License Compliance Manager",
    "License Compliance Analyst",
    "Software Asset Management Analyst",
    "SAM Analyst",
    "Software License Manager",
    "ITAM Specialist",
    "SAM Consultant",
    "Software Asset Management Consultant",
    "ServiceNow SAM",
    "Flexera",
    "Snow Software",
    "Oracle License Compliance",
]
LINKEDIN_LOCATION = "Atlanta Metropolitan Area"
LINKEDIN_GEO_ID = 90000539
LINKEDIN_JOB_TYPE = "F"
LINKEDIN_JOB_POSTING_DATE = "r86400"
LINKEDIN_F_WT = None  # No work type filter — returns all (on-site, remote, hybrid)

CAREERS_FUTURE_SEARCH_QUERIES = ["IT Support", "Full Stack Web Developer", "Application Support", "Cybersecurity Analyst", "fresher developer"]
CAREERS_FUTURE_SEARCH_CATEGORIES = ["Information Technology"]
CAREERS_FUTURE_SEARCH_EMPLOYMENT_TYPES = ["Full Time"]

JSEARCH_SEARCH_QUERIES = [
    "Software License Compliance in United States",
    "License Compliance Manager in United States",
    "SAM Analyst in United States",
    "Software Asset Management Analyst in United States",
    "ITAM Specialist in United States",
    "Software License Manager in United States",
]
JSEARCH_DATE_POSTED = "3days"  # options: all, today, 3days, week, month
JSEARCH_REMOTE_ONLY = False    # False = includes Atlanta on-site + US remote

# --- USAJobs Configuration ---
USAJOBS_API_KEY = os.environ.get("USAJOBS_API_KEY")
USAJOBS_API_EMAIL = os.environ.get("USAJOBS_API_EMAIL")  # Required as User-Agent header
USAJOBS_SEARCH_QUERIES = [
    "Software Asset Management",
    "Software License Management",
    "IT Asset Management",
    "License Compliance",
    "SAM Analyst",
]
USAJOBS_LOCATION = "Atlanta, GA"
USAJOBS_RADIUS = 50         # miles
USAJOBS_DATE_POSTED = 1     # days (1 = last 24h)

# --- Pre-filter Configuration ---
PRE_FILTER_ENABLED = True
PRE_FILTER_MODEL = "anthropic/claude-haiku-4-5-20251001"  # Fast/cheap Anthropic model for relevance check
PRE_FILTER_FETCH_MULTIPLIER = 4  # fetch 4x jobs, filter down to JOBS_TO_SCORE_PER_RUN

# --- Processing Limits ---
SCRAPING_SOURCES = ["linkedin", "jsearch", "usajobs"]
JOBS_TO_SCORE_PER_RUN = 5
JOBS_TO_CUSTOMIZE_PER_RUN = 1
MAX_JOBS_PER_SEARCH = {
    "linkedin": 2,
    "careers_future": 10,
    "jsearch": 10,
    "usajobs": 10,
}

# =================================================================
# 3. ADVANCED SYSTEM SETTINGS (Modify with Caution)
# =================================================================
LLM_MAX_RPM = 10
LLM_MAX_RETRIES = 3
LLM_RETRY_BASE_DELAY = 10
LLM_DAILY_REQUEST_BUDGET = 0
LLM_REQUEST_DELAY_SECONDS = 8

LINKEDIN_MAX_START = 1
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 15

JOB_EXPIRY_DAYS = 30
JOB_CHECK_DAYS = 3
JOB_DELETION_DAYS = 60
JOB_CHECK_LIMIT = 50
ACTIVE_CHECK_TIMEOUT = 20
ACTIVE_CHECK_MAX_RETRIES = 2
ACTIVE_CHECK_RETRY_DELAY = 10
