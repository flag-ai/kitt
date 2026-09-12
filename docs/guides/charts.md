# Charts and Visualization

KITT can generate charts from stored benchmark results using Matplotlib. This is
useful for visualizing quantization quality tradeoffs, comparing engine
performance, and tracking metric trends over time.

---

## Installation

Charts require the optional `charts` extra:

```bash
poetry install -E charts
```

This pulls in Matplotlib and its dependencies.

---

## Quantization Curves

Generate a chart showing how quantization levels affect quality metrics across
model families:

```bash
kitt charts quant-curves
```

Filter by model family:

```bash
kitt charts quant-curves --model-family Llama-3
```

Change the output file:

```bash
kitt charts quant-curves --output llama3_quant.svg
```

Export the underlying data as CSV instead of rendering a chart:

```bash
kitt charts quant-curves --csv
```

---

## Output Formats

Charts are saved as SVG by default. The output format is determined by the file
extension you provide:

| Extension | Format |
|-----------|--------|
| `.svg` | Scalable Vector Graphics (default) |
| `.png` | Raster image |
| `.pdf` | PDF document |

Example:

```bash
kitt charts quant-curves --output curves.png
```

---

## Data Sources

Chart commands read from the KITT storage backend. KITT tries SQLite first
(`SQLiteStore`) and falls back to the JSON store (`JsonStore`). Make sure you
have stored results (via `kitt run` or the storage commands) before
generating charts.

---

## Chart Types

| Command | Description |
|---------|-------------|
| `kitt charts quant-curves` | Quality vs. quantization level curves |

Additional chart types may be added through the plugin system. The chart
generation logic lives in `src/kitt/reporters/quant_curves.py` and uses the
same result store interface as the rest of KITT.
