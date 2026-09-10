"""GET-only BetterHotel transport. No environment proxy, redirects or writes."""

from __future__ import annotations
import asyncio, email.utils, math, random, time
from functools import wraps
from urllib.parse import quote
import httpx
from datetime import datetime, timezone
from kajovokarty.domain.core import AppError, digest, require

BASE = "https://api.better-hotel.com/api/connector/v/1"
TEMPLATES = [
    "/currency",
    "/invoice",
    "/invoice/{invoice_id}",
    "/reservation",
    "/reservation/{reservation_id}",
    "/reservation/{reservation_id}/invoice",
    "/reservation/{reservation_id}/bill",
    "/bill/{bill_id}",
    "/bill/{bill_id}/bill-item",
    "/bill-item/{item_id}",
    "/reservation/{reservation_id}/security-deposit",
    "/financial-stats",
]


RESERVATION_EXPAND = [
    ("expand[]", "reservation_source"),
    ("expand[]", "reservation_note"),
]


def request_shape(template):
    """Projection identity excludes dates, cursor and count (SSOT 8.3)."""
    return digest(
        {
            "endpoint_template": template,
            "expand": [v for _, v in RESERVATION_EXPAND]
            if template in ("/reservation", "/reservation/{reservation_id}")
            else [],
            "filters": [],
        }
    )


def validated(fn):
    @wraps(fn)
    def call(self, template, *args, **kwargs):
        try:
            return fn(self, template, *args, **kwargs)
        except AppError as error:
            self.fail(template, error.code)
            raise

    return call


class TokenBucket:
    def __init__(self, rate, capacity=10, clock=time.monotonic):
        self.rate, self.capacity, self.clock = float(rate), capacity, clock
        self.tokens = float(capacity)
        self.updated = clock()

    def acquire(self, wait):
        current = self.clock()
        self.tokens = min(
            self.capacity, self.tokens + (current - self.updated) * self.rate
        )
        self.updated = current
        delay = max(0, (1 - self.tokens) / self.rate)
        if delay:
            wait(delay)
            current = self.clock()
            self.tokens = min(
                self.capacity, self.tokens + (current - self.updated) * self.rate
            )
            self.updated = current
        self.tokens = max(0, self.tokens - 1)


class BetterHotelClient:
    def __init__(
        self,
        access,
        client,
        settings=None,
        cancel=None,
        transport=None,
        proxy_auth=None,
    ):
        require(
            access
            and client
            and "\n" not in access + client
            and "\r" not in access + client,
            "API_AUTH",
            "Vyplňte oba tokeny v Nastavení.",
        )
        self.settings = dict(settings or {})
        self.evidence_class = (
            "LOCAL_CONTRACT_TEST" if transport is not None else "LIVE_OBSERVATION"
        )
        self.attempt_deadline = 120.0
        self.loop = asyncio.new_event_loop()
        self.bucket = TokenBucket(self.settings.get("sync.requests_per_second", "2"))
        self.last_template = None
        self.logger = None
        self.correlation_id = None
        self.cancel = cancel
        self.stats = {}
        self.last_request = 0
        proxy_url = self.settings.get("network.proxy_url")
        proxy = httpx.Proxy(proxy_url, auth=proxy_auth) if proxy_url else None
        self.client = httpx.AsyncClient(
            headers={
                "Accept": "application/json",
                "X-Access-Token": access,
                "X-Client-Token": client,
            },
            timeout=self.settings.get("sync.timeout_seconds", 30),
            follow_redirects=False,
            trust_env=False,
            transport=transport,
            proxy=proxy,
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
        )

    def close(self):
        if not self.loop.is_closed():
            try:
                self.loop.run_until_complete(self.client.aclose())
            finally:
                self.loop.close()

    def check_cancel(self):
        require(
            not (self.cancel and self.cancel.is_set()),
            "CANCELLED",
            "Operace byla zrušena.",
        )

    def wait(self, seconds):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            self.check_cancel()
            time.sleep(min(0.1, max(0, until - time.monotonic())))

    def fail(self, template, code):
        stat = self.stats.get(template)
        if stat is not None:
            stat["state"] = "FAIL"
            if code not in stat["error_codes"]:
                stat["error_codes"].append(code)

    async def _attempt(self, url, params):
        async with asyncio.timeout(self.attempt_deadline):
            return await self.client.get(url, params=params or [])

    @validated
    def get(self, template, ids=None, params=None):
        require(template in TEMPLATES, "API_SCHEMA", "Neznámá šablona endpointu.")
        self.last_template = template
        url = BASE + template
        for key, value in (ids or {}).items():
            url = url.replace("{" + key + "}", quote(str(value), safe=""))
        require("{" not in url, "API_SCHEMA", "Chybí ID endpointu.")
        stat = self.stats.setdefault(
            template,
            {
                "response_count": 0,
                "item_count": 0,
                "status_codes": [],
                "response_hashes": [],
                "field_types": {},
                "error_codes": [],
                "state": "NOT_ATTEMPTED",
            },
        )
        for attempt in range(self.settings.get("sync.retry_count", 3) + 1):
            self.check_cancel()
            self.bucket.acquire(self.wait)
            self.check_cancel()
            started = time.monotonic()
            try:
                response = self.loop.run_until_complete(self._attempt(url, params))
                status = response.status_code
                if self.logger:
                    self.logger.write(
                        {
                            "endpoint_template": template,
                            "http_status": status,
                            "elapsed_ms": round((time.monotonic() - started) * 1000),
                            "correlation_id": self.correlation_id,
                        }
                    )
                stat["status_codes"].append(status)
                if status in (401, 403):
                    raise AppError(
                        "API_AUTH", "Ověřte oba přístupové tokeny v Nastavení."
                    )
                if status == 429:
                    retry = response.headers.get("Retry-After", "1")
                    try:
                        seconds = float(retry)
                    except ValueError:
                        try:
                            seconds = (
                                email.utils.parsedate_to_datetime(retry)
                                - datetime.now(timezone.utc)
                            ).total_seconds()
                        except (ValueError, TypeError, OverflowError):
                            seconds = 1
                    if not math.isfinite(seconds):
                        seconds = 1
                    require(
                        seconds <= 60,
                        "API_RATE_LIMIT",
                        "Server požaduje čekání delší než 60 sekund.",
                        retry,
                    )
                    if attempt < self.settings.get("sync.retry_count", 3):
                        self.wait(max(0, seconds))
                        continue
                    raise AppError("API_RATE_LIMIT", "Server omezil počet požadavků.")
                if status in (500, 502, 503, 504) and attempt < self.settings.get(
                    "sync.retry_count", 3
                ):
                    self.wait(0.5 * 2**attempt + random.uniform(0, 0.2))
                    continue
                require(
                    status == 200,
                    "API_HTTP",
                    "Server nevrátil očekávanou odpověď.",
                    {"status": status},
                )
                try:
                    body = response.json()
                except ValueError:
                    raise AppError("API_SCHEMA", "Odpověď není platný JSON.")
                require(
                    isinstance(body, (dict, list)),
                    "API_SCHEMA",
                    "Neplatná JSON obálka.",
                )
                stat["response_count"] += 1
                stat["response_hashes"].append(digest(body))
                data = body.get("data", body) if isinstance(body, dict) else body
                items = data if isinstance(data, list) else [data] if data else []
                stat["item_count"] += len(items)
                if stat["state"] != "FAIL":
                    stat["state"] = (
                        "PASS_NONEMPTY" if stat["item_count"] else "PASS_EMPTY"
                    )
                for item in items:
                    if isinstance(item, dict):
                        for k, v in item.items():
                            stat["field_types"].setdefault(k, [])
                            t = type(v).__name__
                            stat["field_types"][k] = sorted(
                                set(stat["field_types"][k] + [t])
                            )
                return body
            except (httpx.TransportError, TimeoutError):
                if attempt < self.settings.get("sync.retry_count", 3):
                    self.wait(0.5 * 2**attempt + random.uniform(0, 0.2))
                    continue
                e = AppError(
                    "API_NETWORK", "Síťová chyba při čtení BetterHotel.", retryable=True
                )
                stat["state"] = "FAIL"
                stat["error_codes"].append(e.code)
                raise e
            except AppError as e:
                stat["state"] = "FAIL"
                stat["error_codes"].append(e.code)
                raise

    @validated
    def collection(self, template, ids=None, params=None):
        base = list(params or [])
        seen = set()
        cursor = None
        result = []
        while True:
            query = list(base)
            if template in ("/invoice", "/reservation") or cursor:
                query.append(("count", 25))
            if cursor:
                query.append(("cursor", cursor))
            body = self.get(template, ids, query)
            require(
                isinstance(body, dict) and "data" in body,
                "API_SCHEMA",
                "Kolekci chybí data.",
            )
            data = body["data"]
            data = [data] if isinstance(data, dict) else data
            require(
                isinstance(data, list) and all(isinstance(x, dict) for x in data),
                "API_SCHEMA",
                "Neplatná kolekce.",
            )
            result.extend(data)
            meta = body.get("meta", {})
            require(isinstance(meta, dict), "API_SCHEMA", "Neplatná metadata.")
            if "total_count" in meta:
                require(
                    type(meta["total_count"]) is int and meta["total_count"] >= 0,
                    "API_SCHEMA",
                    "Neplatný počet záznamů.",
                )
            more = meta.get("has_more", False)
            require(type(more) is bool, "API_SCHEMA", "has_more musí být boolean.")
            if not more:
                return result
            cursor = meta.get("cursor")
            require(
                isinstance(cursor, str) and cursor and cursor not in seen,
                "API_CURSOR_CYCLE",
                "Neplatný nebo opakovaný stránkovací kurzor.",
            )
            seen.add(cursor)

    @validated
    def detail(self, template, ids):
        body = self.get(
            template,
            ids,
            RESERVATION_EXPAND if template == "/reservation/{reservation_id}" else None,
        )
        data = body.get("data", body) if isinstance(body, dict) else body
        if isinstance(data, list):
            require(
                len(data) == 1,
                "API_SCHEMA",
                "Detail musí obsahovat právě jeden objekt.",
            )
            data = data[0]
        require(
            isinstance(data, dict)
            and (data.get("id") is not None or data.get("uuid") is not None),
            "API_SCHEMA",
            "Detail chybí nebo je neúplný.",
        )
        return data
