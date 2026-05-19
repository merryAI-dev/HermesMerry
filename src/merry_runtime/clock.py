from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


KST = ZoneInfo("Asia/Seoul")


def now_kst_datetime() -> datetime:
    return datetime.now(KST)


def now_kst() -> str:
    return now_kst_datetime().isoformat()


def compact_kst_timestamp() -> str:
    return now_kst_datetime().strftime("%Y%m%dT%H%M%S%z")
