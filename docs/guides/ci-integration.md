# CI/CD Integration

KITT integrates with CI/CD pipelines to automate benchmark runs, post results as
PR comments, and gate deployments on performance thresholds.

---

## CI Report Command

The `kitt ci report` command generates a summary from benchmark results and
optionally posts it to a GitHub pull request:

```bash
kitt ci report \
    --results-dir ./benchmark-output \
    --baseline-dir ./baseline-results \
    --github-token "$GITHUB_TOKEN" \
    --repo owner/repo \
    --pr 42
```

| Flag | Description |
|------|-------------|
| `--results-dir` | Directory containing the latest benchmark `metrics.json` |
| `--baseline-dir` | Previous results to compare against (optional) |
| `--github-token` | GitHub API token for posting comments |
| `--repo` | Repository in `owner/repo` format |
| `--pr` | Pull request number |
| `--output` | Write the report to a local file instead of posting |

When both `--results-dir` and `--baseline-dir` are provided, the report includes
a comparison showing regressions and improvements.

If a KITT comment already exists on the PR (identified by a hidden HTML marker),
it is updated in place rather than creating a duplicate.

---

## GitHub Actions Workflow

Below is a complete workflow that runs benchmarks on every pull request and
posts results as a comment:

```yaml
name: KITT Benchmark

on:
  pull_request:
    branches: [main]

jobs:
  benchmark:
    runs-on: [self-hosted, gpu]
    steps:
      - uses: actions/checkout@v4

      - name: Install KITT
        run: pip install kitt-bench

      - name: Pull engine image
        run: kitt engines setup vllm

      - name: Run benchmarks
        run: |
          kitt run \
            -m ./models/llama-3-8b \
            -e vllm \
            -s quick \
            -o ./results

      - name: Post CI report
        if: github.event_name == 'pull_request'
        run: |
          kitt ci report \
            --results-dir ./results \
            --github-token "${{ secrets.GITHUB_TOKEN }}" \
            --repo "${{ github.repository }}" \
            --pr "${{ github.event.pull_request.number }}"

      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: benchmark-results
          path: ./results/
```

---

## Using a Baseline

To detect regressions, store baseline results as a build artifact or in a
dedicated branch and compare against them:

```yaml
      - name: Download baseline
        uses: actions/download-artifact@v4
        with:
          name: benchmark-baseline
          path: ./baseline
        continue-on-error: true

      - name: Post report with comparison
        run: |
          kitt ci report \
            --results-dir ./results \
            --baseline-dir ./baseline \
            --github-token "${{ secrets.GITHUB_TOKEN }}" \
            --repo "${{ github.repository }}" \
            --pr "${{ github.event.pull_request.number }}"
```

---

## Artifact Collection

Benchmark runs produce the following files under the output directory:

| File | Contents |
|------|----------|
| `metrics.json` | Raw benchmark metrics |
| `summary.md` | Human-readable Markdown summary |
| `hardware.json` | Hardware fingerprint of the runner |
| `config.json` | Configuration used for the run |

Upload these as workflow artifacts to preserve a history of benchmark results
across builds.

---

## Local Report Generation

Generate a report file without posting to GitHub:

```bash
kitt ci report --results-dir ./results --output report.md
```

This is useful for local review or integration with other reporting systems.

---

## Exit Codes

KITT commands use standard exit codes so CI systems can detect failures:

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Benchmark failure, missing results, or API error |

Use these exit codes to gate merge or deployment steps in your pipeline.
