"""kitt run - Execute benchmarks against a model."""

import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from kitt import __version__

console = Console()
logger = logging.getLogger(__name__)


@click.command()
@click.option(
    "--model",
    "-m",
    required=True,
    help="Path to model or model identifier",
)
@click.option(
    "--engine",
    "-e",
    required=True,
    help="Inference engine to use (vllm, llama_cpp, ollama, exllamav2, mlx)",
)
@click.option(
    "--suite",
    "-s",
    default="quick",
    help="Test suite to run (quick, standard, performance)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Output directory for results",
)
@click.option(
    "--skip-warmup",
    is_flag=True,
    help="Skip warmup phase for all benchmarks",
)
@click.option(
    "--runs",
    type=int,
    default=None,
    help="Override number of runs per benchmark",
)
@click.option(
    "--config",
    type=click.Path(exists=True),
    help="Path to custom configuration file",
)
@click.option(
    "--store-karr",
    is_flag=True,
    help="Store results in KARR repository",
)
@click.option(
    "--auto-pull",
    is_flag=True,
    help="Automatically pull/build engine image if not available",
)
@click.option(
    "--mode",
    type=click.Choice(["docker", "native"]),
    default=None,
    help="Engine execution mode (docker or native). Uses engine default if not set.",
)
def run(
    model, engine, suite, output, skip_warmup, runs, config, store_karr, auto_pull, mode
):
    """Run benchmarks against a model using a specified engine."""
    from kitt.benchmarks.registry import BenchmarkRegistry
    from kitt.config.loader import load_suite_config
    from kitt.engines.registry import EngineRegistry
    from kitt.hardware.fingerprint import HardwareFingerprint
    from kitt.reporters.json_reporter import save_json_report
    from kitt.reporters.markdown import generate_summary
    from kitt.runners.suite import SuiteRunner
    from kitt.utils.compression import ResultCompression

    # Discover engines
    EngineRegistry.auto_discover()

    # Validate engine
    all_engines = EngineRegistry.list_all()
    if engine not in all_engines:
        console.print(
            f"[red]Engine '{engine}' not found.[/red] "
            f"Available: {', '.join(all_engines)}"
        )
        raise SystemExit(1)

    engine_cls = EngineRegistry.get_engine(engine)
    if not engine_cls.is_available():
        if auto_pull:
            console.print(
                f"[yellow]Engine '{engine}' not available — auto-pulling...[/yellow]"
            )
            try:
                engine_cls.setup()
            except Exception as e:
                console.print(f"[red]Auto-pull failed: {e}[/red]")
                raise SystemExit(1) from e
        else:
            diag = engine_cls.diagnose()
            console.print(f"[red]Engine '{engine}' is not available.[/red]")
            if diag.error:
                console.print(f"  {diag.error}")
            if diag.guidance:
                console.print(f"  Fix: {diag.guidance}")
            raise SystemExit(1)

    # Preflight: validate model format compatibility
    format_error = engine_cls.validate_model(model)
    if format_error:
        console.print(f"[red]Model/engine mismatch:[/red] {format_error}")
        raise SystemExit(1)

    console.print("[bold]KITT Benchmark Runner[/bold]")
    console.print(f"  Model:  {model}")
    console.print(f"  Engine: {engine}")
    console.print(f"  Suite:  {suite}")
    console.print()

    # Load suite config
    suite_config_path = _find_suite_config(suite)
    suite_cfg = None
    if suite_config_path:
        suite_cfg = load_suite_config(suite_config_path)
        console.print(f"  Loaded suite: {suite_cfg.suite_name} v{suite_cfg.version}")
    else:
        console.print(
            f"[yellow]Suite config '{suite}' not found, using defaults[/yellow]"
        )

    # Detect hardware
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Detecting hardware...", total=None)
        system_info = HardwareFingerprint.detect_system()
        fingerprint = HardwareFingerprint._format_fingerprint(system_info)
        progress.update(task, description="Hardware detected")

    # Initialize engine
    console.print(f"\n[cyan]Initializing {engine} engine...[/cyan]")
    engine_instance = engine_cls()
    engine_config = {}
    if config:
        import yaml

        with open(config) as f:
            engine_config = yaml.safe_load(f) or {}

    if mode:
        engine_config["mode"] = mode

    try:
        engine_instance.initialize(model, engine_config)
    except Exception as e:
        console.print(f"[red]Failed to initialize engine: {e}[/red]")
        raise SystemExit(1) from e

    # Load benchmarks
    BenchmarkRegistry.auto_discover()
    benchmarks = []

    if suite_config_path and suite_cfg:
        for test_name in suite_cfg.tests:
            try:
                bench_cls = BenchmarkRegistry.get_benchmark(test_name)
                benchmarks.append(bench_cls())
            except ValueError:
                console.print(
                    f"[yellow]Benchmark '{test_name}' not found, skipping[/yellow]"
                )
    else:
        # Default: run throughput only
        bench_cls = BenchmarkRegistry.get_benchmark("throughput")
        benchmarks.append(bench_cls())

    if not benchmarks:
        console.print("[red]No benchmarks to run[/red]")
        engine_instance.cleanup()
        raise SystemExit(1)

    # Build global config
    global_config = {}
    if skip_warmup:
        global_config["warmup"] = {"enabled": False}
    if runs is not None:
        global_config["runs"] = runs

    # Run suite
    console.print(
        f"\n[bold green]Running {len(benchmarks)} benchmark(s)...[/bold green]\n"
    )
    runner = SuiteRunner(engine_instance)

    suite_result = runner.run(
        suite_name=suite,
        benchmarks=benchmarks,
        global_config=global_config,
    )

    # Cleanup engine
    engine_instance.cleanup()

    # Generate output directory
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    model_name_clean = Path(model).name if "/" in model or "\\" in model else model
    output_dir = (
        Path(output)
        if output
        else Path.home() / ".kitt" / "results" / model_name_clean / engine / timestamp
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save JSON metrics report
    save_json_report(
        suite_result,
        output_dir / "metrics.json",
        system_info=system_info,
        engine_name=engine,
        model_name=model,
    )

    # Save hardware info separately
    hardware_data = asdict(system_info)
    with open(output_dir / "hardware.json", "w") as f:
        json.dump(hardware_data, f, indent=2)

    # Save configuration used
    run_config = {
        "model": model,
        "engine": engine,
        "suite": suite,
        "skip_warmup": skip_warmup,
        "runs_override": runs,
        "timestamp": timestamp,
        "kitt_version": __version__,
    }
    with open(output_dir / "config.json", "w") as f:
        json.dump(run_config, f, indent=2)

    # Save markdown summary
    summary = generate_summary(
        suite_result,
        system_info=system_info,
        engine_name=engine,
        model_name=model,
    )
    (output_dir / "summary.md").write_text(summary)

    # Compress and save outputs
    all_outputs = []
    for result in suite_result.results:
        for output_item in result.outputs:
            all_outputs.append(
                {
                    "benchmark": result.test_name,
                    "run_number": result.run_number,
                    **output_item,
                }
            )

    if all_outputs:
        outputs_dir = output_dir / "outputs"
        outputs_dir.mkdir(exist_ok=True)
        chunk_files = ResultCompression.save_outputs(
            all_outputs, outputs_dir / "results"
        )
        console.print(f"  Outputs compressed: {len(chunk_files)} chunk(s)")

    # Store in KARR repo if requested
    if store_karr:
        _store_in_karr(output_dir, fingerprint, model_name_clean, engine, timestamp)

    # Print summary
    console.print(f"\n{'=' * 60}")
    status = (
        "[bold green]PASSED[/bold green]"
        if suite_result.passed
        else "[bold red]FAILED[/bold red]"
    )
    console.print(f"Status: {status}")
    console.print(
        f"Results: {suite_result.passed_count}/{suite_result.total_benchmarks} passed"
    )
    console.print(f"Time: {suite_result.total_time_seconds:.1f}s")
    console.print(f"Output: {output_dir}")


def _store_in_karr(
    output_dir: Path,
    fingerprint: str,
    model_name: str,
    engine_name: str,
    timestamp: str,
) -> None:
    """Store results in a KARR repository."""
    from kitt.git_ops.repo_manager import KARRRepoManager

    karr_path = KARRRepoManager.find_results_repo(fingerprint)
    if not karr_path:
        karr_path = Path.cwd() / f"karr-{fingerprint[:40]}"
        console.print(f"[cyan]Creating KARR repository at {karr_path}...[/cyan]")
        KARRRepoManager.create_results_repo(karr_path, fingerprint)

    # Read all files from output_dir
    files: dict[str, str | bytes] = {}
    for file_path in output_dir.rglob("*"):
        if file_path.is_file():
            rel_path = str(file_path.relative_to(output_dir))
            if file_path.suffix in (".gz", ".bin"):
                files[rel_path] = file_path.read_bytes()
            else:
                files[rel_path] = file_path.read_text()

    KARRRepoManager.store_results(karr_path, model_name, engine_name, timestamp, files)
    console.print(f"[green]Results stored in KARR: {karr_path}[/green]")


def _find_suite_config(suite_name: str) -> Path | None:
    """Find suite configuration file."""
    # Check standard locations
    search_paths = [
        Path("configs/suites") / f"{suite_name}.yaml",
        Path(__file__).parent.parent.parent.parent
        / "configs"
        / "suites"
        / f"{suite_name}.yaml",
    ]

    for path in search_paths:
        if path.exists():
            return path

    return None
