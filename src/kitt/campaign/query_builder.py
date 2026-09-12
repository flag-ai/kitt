"""Query builder for metadata-driven campaigns."""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class QueryBuilder:
    """Parse WHERE-style expressions into ResultStore query filters."""

    # Supported operators
    _OPERATORS = {"=", "!=", "LIKE", "like"}

    def parse(self, expression: str) -> dict[str, Any]:
        """Parse a WHERE-style expression into query filters.

        Supported syntax:
            engine=vllm AND model LIKE 'Qwen%'
            passed=true AND suite_name=standard

        Args:
            expression: SQL-like WHERE clause.

        Returns:
            Dict of filter key-value pairs for ResultStore.query().
        """
        filters: dict[str, Any] = {}

        if not expression or not expression.strip():
            return filters

        # Split on AND (case-insensitive)
        parts = re.split(r"\s+AND\s+", expression, flags=re.IGNORECASE)

        for part in parts:
            part = part.strip()
            if not part:
                continue

            key, value = self._parse_condition(part)
            if key is not None:
                filters[key] = value

        return filters

    def _parse_condition(self, condition: str) -> tuple[str | None, Any]:
        """Parse a single condition like 'engine=vllm' or 'passed=true'."""
        # Try LIKE pattern
        like_match = re.match(
            r"(\w+)\s+(?:LIKE|like)\s+'([^']*)'",
            condition,
        )
        if like_match:
            key = like_match.group(1)
            # LIKE patterns become exact match (simplified for dict filters)
            value = like_match.group(2).replace("%", "")
            return key, value

        # Try equality: key=value or key='value'
        eq_match = re.match(r"(\w+)\s*=\s*'?([^']*?)'?\s*$", condition)
        if eq_match:
            key = eq_match.group(1)
            value = eq_match.group(2)

            # Type coercion
            if value.lower() == "true":
                value = True
            elif value.lower() == "false":
                value = False
            elif value.isdigit():
                value = int(value)

            return key, value

        # Try inequality: key!=value
        neq_match = re.match(r"(\w+)\s*!=\s*'?([^']*?)'?\s*$", condition)
        if neq_match:
            logger.debug(f"Inequality not supported in simple filters: {condition}")
            return None, None

        logger.warning(f"Unparseable condition: {condition}")
        return None, None
