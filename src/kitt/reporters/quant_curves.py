"""Quantization quality curve generation."""

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Bits per parameter for common quantization types
_QUANT_BPP = {
    "F16": 16.0,
    "BF16": 16.0,
    "F32": 32.0,
    "Q8_0": 8.0,
    "Q6_K": 6.57,
    "Q5_K_M": 5.69,
    "Q5_K_S": 5.54,
    "Q5_0": 5.0,
    "Q4_K_M": 4.85,
    "Q4_K_S": 4.59,
    "Q4_0": 4.0,
    "Q3_K_L": 3.94,
    "Q3_K_M": 3.65,
    "Q3_K_S": 3.50,
    "Q2_K": 3.35,
    "IQ4_XS": 4.25,
    "IQ3_XXS": 3.06,
    "IQ2_XXS": 2.06,
    "Q4_0_4_4": 4.0,
    "Q4_0_4_8": 4.0,
    "Q4_0_8_8": 4.0,
}


class QuantCurveGenerator:
    """Generate quality-vs-size tradeoff charts for quantized models."""

    def __init__(self, result_store=None) -> None:
        self.store = result_store

    def gather_data(
        self,
        model_family: str | None = None,
    ) -> list[dict[str, Any]]:
        """Gather quant curve data from results.

        Args:
            model_family: Filter by model family (e.g. "Llama-3").

        Returns:
            List of data points with quant, bpp, accuracy, throughput.
        """
        if not self.store:
            return []

        filters = {}
        if model_family:
            filters["model"] = model_family

        results = self.store.query(
            filters=filters or None,
            order_by="-timestamp",
            limit=200,
        )

        points = []
        for r in results:
            quant = r.get("quant", "")
            if not quant:
                continue

            bpp = _QUANT_BPP.get(quant)
            if bpp is None:
                continue

            metrics = r.get("metrics", {})
            accuracy = metrics.get("accuracy", 0)
            throughput = metrics.get("avg_tps", 0)

            points.append(
                {
                    "model": r.get("model", ""),
                    "engine": r.get("engine", ""),
                    "quant": quant,
                    "bpp": bpp,
                    "accuracy": accuracy,
                    "throughput": throughput,
                }
            )

        return points

    def generate_curve(
        self,
        model_family: str | None = None,
        output_path: str | None = None,
    ) -> str | None:
        """Generate a quality-vs-size curve chart.

        Args:
            model_family: Filter by model family.
            output_path: Path to save SVG/PNG. If None, displays interactively.

        Returns:
            Path to saved file, or None.
        """
        data = self.gather_data(model_family=model_family)
        if not data:
            logger.warning("No data for quant curves")
            return None

        try:
            import matplotlib

            matplotlib.use("Agg")  # Non-interactive backend
            import matplotlib.pyplot as plt
        except ImportError:
            logger.error("matplotlib is required for chart generation")
            return None

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

        # Group by model
        models: dict[str, Any] = {}
        for p in data:
            key = p["model"]
            if key not in models:
                models[key] = []
            models[key].append(p)

        for model_name, points in models.items():
            points.sort(key=lambda x: x["bpp"])
            bpps = [p["bpp"] for p in points]
            accs = [p["accuracy"] for p in points]
            tpss = [p["throughput"] for p in points]

            ax1.plot(bpps, accs, "o-", label=model_name, markersize=6)
            ax2.plot(bpps, tpss, "s-", label=model_name, markersize=6)

        ax1.set_xlabel("Bits per Parameter")
        ax1.set_ylabel("Accuracy")
        ax1.set_title("Quality vs Quantization")
        ax1.legend(fontsize=8)
        ax1.grid(True, alpha=0.3)

        ax2.set_xlabel("Bits per Parameter")
        ax2.set_ylabel("Throughput (tokens/sec)")
        ax2.set_title("Performance vs Quantization")
        ax2.legend(fontsize=8)
        ax2.grid(True, alpha=0.3)

        fig.suptitle(
            f"Quantization Tradeoff Curves{' — ' + model_family if model_family else ''}"
        )
        plt.tight_layout()

        if output_path:
            fig.savefig(output_path, dpi=150, bbox_inches="tight")
            plt.close(fig)
            logger.info(f"Chart saved to {output_path}")
            return output_path
        else:
            plt.close(fig)
            return None

    def compare_model_families(
        self,
        families: list[str],
        output_path: str | None = None,
    ) -> str | None:
        """Compare quant curves across model families.

        Args:
            families: List of model family names to compare.
            output_path: Path to save chart.

        Returns:
            Path to saved file, or None.
        """
        all_data = []
        for family in families:
            data = self.gather_data(model_family=family)
            all_data.extend(data)

        if not all_data:
            logger.warning("No data for comparison")
            return None

        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            logger.error("matplotlib required")
            return None

        fig, ax = plt.subplots(figsize=(10, 6))

        models: dict[str, Any] = {}
        for p in all_data:
            key = p["model"]
            if key not in models:
                models[key] = []
            models[key].append(p)

        for model_name, points in models.items():
            points.sort(key=lambda x: x["bpp"])
            bpps = [p["bpp"] for p in points]
            accs = [p["accuracy"] for p in points]
            ax.plot(bpps, accs, "o-", label=model_name, markersize=6)

        ax.set_xlabel("Bits per Parameter")
        ax.set_ylabel("Accuracy")
        ax.set_title("Model Family Comparison")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

        plt.tight_layout()

        if output_path:
            fig.savefig(output_path, dpi=150, bbox_inches="tight")
            plt.close(fig)
            return output_path
        else:
            plt.close(fig)
            return None

    def export_csv(
        self,
        model_family: str | None = None,
        output_path: str = "quant_curves.csv",
    ) -> str:
        """Export curve data as CSV.

        Returns:
            Path to CSV file.
        """
        data = self.gather_data(model_family=model_family)
        lines = ["model,engine,quant,bpp,accuracy,throughput"]
        for p in data:
            lines.append(
                f"{p['model']},{p['engine']},{p['quant']},"
                f"{p['bpp']},{p['accuracy']},{p['throughput']}"
            )
        Path(output_path).write_text("\n".join(lines))
        return output_path
