import os
import time
import logging
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# ── Configuration (from .env) ──────────────────────────────────
# Comma-separated list of URLs to ping, e.g.:
#   API_URLS=https://api-one.com/ping,https://api-two.com/ping
_raw_urls               = os.getenv("API_URLS", "https://your-api-endpoint.com/ping")
API_URLS                = [u.strip() for u in _raw_urls.split(",") if u.strip()]
LOG_FILE                = os.getenv("LOG_FILE", "ping_log.txt")
RETRY_INTERVAL_SECONDS  = int(os.getenv("RETRY_INTERVAL_SECONDS", 3600))
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", 30))
# ──────────────────────────────────────────────────────────────

# Set up logging (file + console)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def call_api(url: str) -> bool:
    """Call a single API endpoint. Returns True on success, False on failure."""
    try:
        logger.info(f"Calling API: GET {url}")
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        logger.info(f"[{url}] Success — HTTP {response.status_code}")
        return True
    except requests.exceptions.Timeout:
        logger.error(f"[{url}] Request timed out.")
    except requests.exceptions.ConnectionError as e:
        logger.error(f"[{url}] Connection error: {e}")
    except requests.exceptions.HTTPError as e:
        logger.error(f"[{url}] HTTP error: {e} (status {e.response.status_code})")
    except requests.exceptions.RequestException as e:
        logger.error(f"[{url}] Unexpected request error: {e}")
    return False


def seconds_until_next_midnight() -> float:
    """Return the number of seconds until the next 00:00:00 AM."""
    now = datetime.now()
    tomorrow_midnight = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return (tomorrow_midnight - now).total_seconds()


def run():
    logger.info(f"Ping scheduler started. URLs to ping: {API_URLS}")

    while True:
        # ── Wait until midnight ──────────────────────────────
        wait_seconds = seconds_until_next_midnight()
        next_run = datetime.now() + timedelta(seconds=wait_seconds)
        logger.info(
            f"Next ping scheduled at {next_run.strftime('%Y-%m-%d %H:%M:%S')} "
            f"({wait_seconds / 3600:.2f} hours away)."
        )
        time.sleep(wait_seconds)

        # ── Attempt pings; retry failed URLs every hour ───────
        pending = list(API_URLS)   # URLs still needing a successful ping
        attempt = 1

        while pending:
            logger.info(f"--- Ping attempt #{attempt} ({len(pending)} URL(s) remaining) ---")

            still_failing = []
            for url in pending:
                if not call_api(url):
                    still_failing.append(url)

            pending = still_failing

            if not pending:
                logger.info("All URLs pinged successfully. Waiting until next midnight.")
                break

            # Some URLs still failing — check if midnight has passed
            time_to_midnight = seconds_until_next_midnight()
            if time_to_midnight <= 0:
                logger.warning(
                    "Midnight passed while retrying. "
                    "Skipping remaining retries; scheduling next daily ping."
                )
                break

            retry_wait = min(RETRY_INTERVAL_SECONDS, time_to_midnight)
            logger.info(
                f"{len(pending)} URL(s) failed: {pending}. "
                f"Retrying in {retry_wait / 60:.0f} minute(s) (attempt #{attempt + 1})."
            )
            time.sleep(retry_wait)
            attempt += 1


if __name__ == "__main__":
    run()
