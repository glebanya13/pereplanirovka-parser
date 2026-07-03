import logging
import time

import requests

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


class RateLimitedSession:
    """Обёртка над requests.Session с паузой между запросами и повтором
    при сетевых ошибках. Суды/агрегаторы медленные и не любят частые
    запросы (см. п.12 ТЗ) — по умолчанию ставим консервативный интервал."""

    def __init__(self, min_interval_seconds: float = 2.5, max_retries: int = 3, timeout: int = 90):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.min_interval = min_interval_seconds
        self.max_retries = max_retries
        self.timeout = timeout
        self._last_request_at = 0.0

    def _wait(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

    def get(self, url: str, encoding: str | None = None, **kwargs) -> requests.Response:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            self._wait()
            try:
                response = self.session.get(url, timeout=self.timeout, **kwargs)
                self._last_request_at = time.monotonic()
                if encoding:
                    response.encoding = encoding
                if response.status_code == 200:
                    return response
                logger.warning("HTTP %s from %s (попытка %s/%s)", response.status_code, url, attempt, self.max_retries)
            except requests.RequestException as exc:
                last_error = exc
                logger.warning("Ошибка запроса к %s (попытка %s/%s): %s", url, attempt, self.max_retries, exc)
            time.sleep(2 ** attempt)
        raise RuntimeError(f"Не удалось получить {url} за {self.max_retries} попыток") from last_error
