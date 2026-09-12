"""Tests for quantization curve generation."""

from unittest.mock import MagicMock, patch

from kitt.reporters.quant_curves import _QUANT_BPP, QuantCurveGenerator


def _make_store_result(model, engine, quant, accuracy=0.8, avg_tps=50.0):
    """Helper to create a mock store result."""
    return {
        "model": model,
        "engine": engine,
        "quant": quant,
        "metrics": {
            "accuracy": accuracy,
            "avg_tps": avg_tps,
        },
    }


class TestGatherData:
    def test_with_no_store_returns_empty(self):
        gen = QuantCurveGenerator(result_store=None)
        assert gen.gather_data() == []

    def test_maps_quant_to_correct_bpp(self):
        store = MagicMock()
        store.query.return_value = [
            _make_store_result("Llama-3.1-8B", "llama_cpp", "Q4_K_M"),
        ]
        gen = QuantCurveGenerator(result_store=store)
        data = gen.gather_data()

        assert len(data) == 1
        assert data[0]["bpp"] == 4.85
        assert data[0]["quant"] == "Q4_K_M"

    def test_filters_by_model_family(self):
        store = MagicMock()
        store.query.return_value = [
            _make_store_result("Llama-3.1-8B", "llama_cpp", "Q4_K_M"),
        ]
        gen = QuantCurveGenerator(result_store=store)
        gen.gather_data(model_family="Llama-3.1")

        # Verify the filter was passed to query
        call_kwargs = store.query.call_args
        filters = call_kwargs.kwargs.get("filters") or call_kwargs[1].get("filters")
        assert filters is not None
        assert filters["model"] == "Llama-3.1"

    def test_skips_unknown_quants(self):
        store = MagicMock()
        store.query.return_value = [
            _make_store_result("model-a", "llama_cpp", "UNKNOWN_QUANT"),
            _make_store_result("model-b", "llama_cpp", "Q4_K_M"),
        ]
        gen = QuantCurveGenerator(result_store=store)
        data = gen.gather_data()

        assert len(data) == 1
        assert data[0]["quant"] == "Q4_K_M"

    def test_skips_results_without_quant(self):
        store = MagicMock()
        store.query.return_value = [
            {"model": "model-a", "engine": "vllm", "quant": "", "metrics": {}},
            _make_store_result("model-b", "llama_cpp", "Q8_0"),
        ]
        gen = QuantCurveGenerator(result_store=store)
        data = gen.gather_data()

        assert len(data) == 1
        assert data[0]["quant"] == "Q8_0"


class TestGenerateCurve:
    def test_returns_none_with_no_data(self):
        gen = QuantCurveGenerator(result_store=None)
        result = gen.generate_curve()
        assert result is None

    def test_saves_file(self, tmp_path):
        store = MagicMock()
        store.query.return_value = [
            _make_store_result("Llama-3.1-8B", "llama_cpp", "Q4_K_M"),
            _make_store_result(
                "Llama-3.1-8B", "llama_cpp", "Q8_0", accuracy=0.85, avg_tps=30
            ),
        ]
        gen = QuantCurveGenerator(result_store=store)
        output = tmp_path / "curve.png"

        mock_fig = MagicMock()
        mock_ax1 = MagicMock()
        mock_ax2 = MagicMock()
        mock_plt = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, (mock_ax1, mock_ax2))

        # Build a mock matplotlib package where matplotlib.pyplot resolves correctly
        mock_matplotlib = MagicMock()
        mock_matplotlib.pyplot = mock_plt

        import sys

        with patch.dict(
            sys.modules,
            {
                "matplotlib": mock_matplotlib,
                "matplotlib.pyplot": mock_plt,
            },
        ):
            result = gen.generate_curve(output_path=str(output))

        assert result == str(output)
        mock_fig.savefig.assert_called_once()


class TestExportCsv:
    def test_creates_csv_file(self, tmp_path):
        store = MagicMock()
        store.query.return_value = [
            _make_store_result(
                "Llama-3.1-8B", "llama_cpp", "Q4_K_M", accuracy=0.8, avg_tps=50
            ),
        ]
        gen = QuantCurveGenerator(result_store=store)
        output = tmp_path / "curves.csv"
        gen.export_csv(output_path=str(output))

        assert output.exists()

    def test_includes_header_row(self, tmp_path):
        store = MagicMock()
        store.query.return_value = [
            _make_store_result("Llama-3.1-8B", "llama_cpp", "Q4_K_M"),
        ]
        gen = QuantCurveGenerator(result_store=store)
        output = tmp_path / "curves.csv"
        gen.export_csv(output_path=str(output))

        content = output.read_text()
        lines = content.strip().split("\n")
        assert lines[0] == "model,engine,quant,bpp,accuracy,throughput"
        assert len(lines) == 2  # header + 1 data row


class TestCompareModelFamilies:
    def test_with_no_data_returns_none(self):
        store = MagicMock()
        store.query.return_value = []
        gen = QuantCurveGenerator(result_store=store)
        result = gen.compare_model_families(["Llama-3.1", "Qwen2.5"])
        assert result is None


class TestQuantBppMapping:
    def test_has_expected_entries(self):
        assert "F16" in _QUANT_BPP
        assert "Q4_K_M" in _QUANT_BPP
        assert "Q8_0" in _QUANT_BPP
        assert "IQ2_XXS" in _QUANT_BPP
        assert _QUANT_BPP["F16"] == 16.0
        assert _QUANT_BPP["Q4_0"] == 4.0
        assert _QUANT_BPP["Q4_0_4_4"] == 4.0
        assert _QUANT_BPP["Q4_0_4_8"] == 4.0
        assert _QUANT_BPP["Q4_0_8_8"] == 4.0
