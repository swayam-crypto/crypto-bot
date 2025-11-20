class RateLimitError(Exception):
    """Raised when CoinGecko returns HTTP 429 (rate limit)."""
    def __init__(self, retry_after: float | None = None):
        self.retry_after = retry_after
        super().__init__("API rate limit exceeded")
