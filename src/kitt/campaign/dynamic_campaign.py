"""Dynamic campaign builder from database queries."""

import logging
from typing import Any

from .models import CampaignConfig, CampaignEngineSpec, CampaignModelSpec

logger = logging.getLogger(__name__)


class DynamicCampaignBuilder:
    """Generate CampaignConfig from query results."""

    def __init__(self, result_store: Any) -> None:
        """Initialize with a ResultStore backend.

        Args:
            result_store: A ResultStore instance.
        """
        self.store = result_store

    def build_from_query(
        self,
        filters: dict[str, Any],
        campaign_name: str | None = None,
        suite: str = "standard",
    ) -> CampaignConfig:
        """Build a campaign config from matching previous results.

        Args:
            filters: Query filters for ResultStore.query().
            campaign_name: Name for the campaign.
            suite: Suite to use for runs.

        Returns:
            CampaignConfig ready for execution.
        """
        results = self.store.query(filters=filters)

        if not results:
            logger.warning("No results match the query filters")

        # Extract unique models and engines
        models_seen: dict[str, CampaignModelSpec] = {}
        engines_seen: dict[str, CampaignEngineSpec] = {}

        for r in results:
            model = r.get("model", "")
            engine = r.get("engine", "")

            if model and model not in models_seen:
                models_seen[model] = CampaignModelSpec(name=model)

            if engine and engine not in engines_seen:
                engines_seen[engine] = CampaignEngineSpec(name=engine, suite=suite)

        name = campaign_name or f"dynamic-{len(models_seen)}m-{len(engines_seen)}e"

        return CampaignConfig(
            campaign_name=name,
            description=f"Auto-generated from query: {filters}",
            models=list(models_seen.values()),
            engines=list(engines_seen.values()),
        )

    def build_from_matching_rules(
        self,
        rules: list[str],
        campaign_name: str | None = None,
        suite: str = "standard",
    ) -> CampaignConfig:
        """Build campaign from a list of matching rule expressions.

        Each rule is a WHERE-style expression. Results matching ANY rule
        are included.

        Args:
            rules: List of query expressions.
            campaign_name: Name for the campaign.
            suite: Suite to use.

        Returns:
            CampaignConfig.
        """
        from .query_builder import QueryBuilder

        builder = QueryBuilder()
        all_results: list[dict[str, Any]] = []
        seen_keys: set = set()

        for rule in rules:
            filters = builder.parse(rule)
            results = self.store.query(filters=filters)
            for r in results:
                key = f"{r.get('model')}|{r.get('engine')}"
                if key not in seen_keys:
                    all_results.append(r)
                    seen_keys.add(key)

        # Build from collected results
        models_seen: dict[str, CampaignModelSpec] = {}
        engines_seen: dict[str, CampaignEngineSpec] = {}

        for r in all_results:
            model = r.get("model", "")
            engine = r.get("engine", "")
            if model and model not in models_seen:
                models_seen[model] = CampaignModelSpec(name=model)
            if engine and engine not in engines_seen:
                engines_seen[engine] = CampaignEngineSpec(name=engine, suite=suite)

        name = campaign_name or f"rules-{len(rules)}"

        return CampaignConfig(
            campaign_name=name,
            description=f"Generated from {len(rules)} matching rules",
            models=list(models_seen.values()),
            engines=list(engines_seen.values()),
        )
