from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from merry_runtime.ingestion.kvic import BUSINESS_TYPE_URL, FUND_TYPE_URL


_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 Chrome/125.0 Safari/537.36 HermesMerry/1.0"
)


@dataclass(frozen=True, slots=True)
class KVICClient:
    api_key: str
    timeout_seconds: int = 15
    user_agent: str = _DEFAULT_USER_AGENT

    def fetch_fund_types(self, *, b_type: str = "0", output_format: str = "1") -> dict[str, Any]:
        return self._get_json(
            BUSINESS_TYPE_URL,
            {
                "bType": b_type,
                "of": output_format,
                "key": self.api_key,
            },
        )

    def fetch_funds(self, *, fund_type: str = "00", output_format: str = "1") -> dict[str, Any]:
        return self._get_json(
            FUND_TYPE_URL,
            {
                "fundType": fund_type,
                "of": output_format,
                "key": self.api_key,
            },
        )

    def _get_json(self, url: str, params: dict[str, str]) -> dict[str, Any]:
        request_url = f"{url}?{urlencode(params)}"
        request = Request(request_url, headers={"User-Agent": self.user_agent, "Accept": "application/json,text/plain,*/*"})
        with urlopen(request, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
