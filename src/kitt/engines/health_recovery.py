"""Engine health recovery — automatic restart on failure."""

import logging
import time
from typing import Any

from .base import GenerationResult, InferenceEngine

logger = logging.getLogger(__name__)


class HealthRecoveryManager:
    """Monitor engine health and restart container on failure.

    Wraps an engine's generate() method with health checking and
    automatic recovery via container restart.
    """

    def __init__(
        self,
        engine: InferenceEngine,
        model_path: str,
        config: dict,
        max_retries: int = 3,
        health_timeout: float = 60.0,
    ) -> None:
        self.engine = engine
        self.model_path = model_path
        self.config = config
        self.max_retries = max_retries
        self.health_timeout = health_timeout
        self._retry_count = 0

    def generate_with_recovery(
        self,
        prompt: str,
        temperature: float = 0.0,
        top_p: float = 1.0,
        top_k: int = 50,
        max_tokens: int = 2048,
        **kwargs: Any,
    ) -> GenerationResult:
        """Generate with automatic recovery on failure.

        If generation fails, attempts to restart the container and retry.

        Returns:
            GenerationResult from the engine.

        Raises:
            RuntimeError: If all retries are exhausted.
        """
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                result = self.engine.generate(
                    prompt=prompt,
                    temperature=temperature,
                    top_p=top_p,
                    top_k=top_k,
                    max_tokens=max_tokens,
                    **kwargs,
                )
                self._retry_count = 0
                return result

            except Exception as e:
                last_error = e
                self._retry_count += 1
                logger.warning(
                    f"Generation failed (attempt {attempt + 1}/{self.max_retries + 1}): {e}"
                )

                if attempt < self.max_retries:
                    self._recover()

        raise RuntimeError(
            f"Generation failed after {self.max_retries + 1} attempts: {last_error}"
        )

    def _recover(self) -> None:
        """Restart the engine container."""
        logger.info("Attempting engine recovery — restarting container")
        try:
            self.engine.cleanup()
        except Exception as e:
            logger.warning(f"Cleanup during recovery failed: {e}")

        time.sleep(2.0)

        try:
            self.engine.initialize(self.model_path, self.config)
            logger.info("Engine recovered successfully")
        except Exception as e:
            logger.error(f"Engine recovery failed: {e}")
            raise

    def check_health(self) -> bool:
        """Check if the engine is healthy by polling its health endpoint."""
        import urllib.error
        import urllib.request

        if not hasattr(self.engine, "_base_url"):
            return True

        health_url = f"{self.engine._base_url}{self.engine.health_endpoint()}"
        try:
            req = urllib.request.Request(health_url)
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status < 500
        except (urllib.error.URLError, OSError, TimeoutError):
            return False

    @property
    def retry_count(self) -> int:
        """Number of retries performed since last successful generation."""
        return self._retry_count
