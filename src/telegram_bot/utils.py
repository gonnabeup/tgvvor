import logging
from datetime import datetime, timezone
import pytz
from .config import TIMEZONES, get_user_timezone

logger = logging.getLogger(__name__)

def setup_logging():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def format_timestamp(dt: datetime, chat_id: int) -> str:
    tz_name = get_user_timezone(chat_id)
    tz = pytz.timezone(tz_name)
    local_dt = dt.astimezone(tz)
    return local_dt.strftime("%Y-%m-%d %H:%M:%S %Z")

def format_hashrate(hashrate: float) -> str:
    if hashrate >= 1_000_000_000_000_000:
        return f"{hashrate / 1_000_000_000_000_000:.2f} PH/s"
    elif hashrate >= 1_000_000_000_000:
        return f"{hashrate / 1_000_000_000_000:.2f} TH/s"
    else:
        return f"{hashrate:.2f} H/s"

def get_worker_short_name(worker_id: str) -> str:
    parts = worker_id.rsplit('.', 1)
    return parts[-1] if len(parts) > 1 else worker_id

def format_uptime(chat_id: int, last_mode_change: dict) -> str:
    current_time = datetime.now(timezone.utc)
    uptime_seconds = (current_time - last_mode_change["timestamp"]).total_seconds()
    hours = int(uptime_seconds // 3600)
    minutes = int((uptime_seconds % 3600) // 60)
    tz_name = get_user_timezone(chat_id)
    return f"{hours} ч {minutes} мин ({tz_name})"