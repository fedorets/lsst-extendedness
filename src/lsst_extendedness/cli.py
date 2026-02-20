"""
Command-line interface for the LSST Extendedness Pipeline.

This module provides the main CLI entry points using Click.

Commands:
- ingest: Run the ingestion pipeline
- query: Interactive query shell
- process: Run post-processing
- db-init: Initialize database
- db-stats: Show database statistics

Example:
    $ lsst-extendedness --help
    $ lsst-extendedness ingest --config config/local.toml
    $ lsst-extendedness db-stats
"""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from lsst_extendedness import __version__
from lsst_extendedness.config import get_settings, load_settings
from lsst_extendedness.storage import SQLiteStorage
from lsst_extendedness.utils.logging import get_logger, setup_logging

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="lsst-extendedness")
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True, path_type=Path),
    help="Configuration file path",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose output",
)
@click.pass_context
def main(ctx: click.Context, config: Path | None, verbose: bool) -> None:
    """LSST Extendedness Pipeline CLI.

    Process LSST astronomical alerts with focus on extendedness analysis
    and solar system object reassociation detection.
    """
    ctx.ensure_object(dict)

    # Load settings
    if config:
        settings = load_settings(config)
    else:
        settings = get_settings()

    ctx.obj["settings"] = settings
    ctx.obj["verbose"] = verbose

    # Setup logging
    log_level = "DEBUG" if verbose else settings.logging.level
    setup_logging(level=log_level, format=settings.logging.format)


@main.command("db-init")
@click.pass_context
def db_init(ctx: click.Context) -> None:
    """Initialize the database schema.

    Creates all tables, indexes, and views if they don't exist.
    Safe to run multiple times.
    """
    settings = ctx.obj["settings"]
    logger = get_logger(__name__)

    db_path = settings.database_path
    console.print(f"Initializing database: [cyan]{db_path}[/cyan]")

    # Ensure directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    storage = SQLiteStorage(db_path)
    storage.initialize()

    logger.info("Database initialized", path=str(db_path))
    console.print("[green]✓[/green] Database initialized successfully")

    storage.close()


@main.command("db-stats")
@click.pass_context
def db_stats(ctx: click.Context) -> None:
    """Show database statistics."""
    settings = ctx.obj["settings"]

    db_path = settings.database_path

    if not db_path.exists():
        console.print(f"[red]Database not found:[/red] {db_path}")
        console.print("Run 'lsst-extendedness db-init' to create it.")
        return

    storage = SQLiteStorage(db_path)
    stats = storage.get_stats()

    # Create table
    table = Table(title="Database Statistics")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    table.add_row("Database Path", str(db_path))
    table.add_row("File Size", f"{stats.get('file_size_mb', 0):.2f} MB")
    table.add_row("", "")
    table.add_row("Alerts (raw)", f"{stats.get('alerts_raw_count', 0):,}")
    table.add_row("Alerts (filtered)", f"{stats.get('alerts_filtered_count', 0):,}")
    table.add_row("Processed Sources", f"{stats.get('processed_sources_count', 0):,}")
    table.add_row("Processing Results", f"{stats.get('processing_results_count', 0):,}")
    table.add_row("Ingestion Runs", f"{stats.get('ingestion_runs_count', 0):,}")
    table.add_row("", "")
    table.add_row("SSO Alerts", f"{stats.get('sso_alerts', 0):,}")
    table.add_row("Reassociations", f"{stats.get('reassociations', 0):,}")

    if "mjd_range" in stats:
        mjd_range = stats["mjd_range"]
        table.add_row("", "")
        table.add_row("MJD Range", f"{mjd_range['min']:.2f} - {mjd_range['max']:.2f}")

    console.print(table)
    storage.close()


@main.command("db-shell")
@click.pass_context
def db_shell(ctx: click.Context) -> None:
    """Open interactive SQLite shell."""
    import subprocess

    settings = ctx.obj["settings"]
    db_path = settings.database_path

    if not db_path.exists():
        console.print(f"[red]Database not found:[/red] {db_path}")
        return

    console.print(f"Opening SQLite shell for: [cyan]{db_path}[/cyan]")
    console.print("Type '.help' for help, '.exit' to quit")

    subprocess.run(["sqlite3", str(db_path)])


@main.command("ingest")
@click.option(
    "--source",
    type=click.Choice(["kafka", "file", "mock"]),
    default="kafka",
    help="Data source type",
)
@click.option(
    "--topic",
    help="Kafka topic (overrides config)",
)
@click.option(
    "--path",
    type=click.Path(exists=True, path_type=Path),
    help="File path for file source",
)
@click.option(
    "--count",
    type=int,
    default=100,
    help="Number of alerts for mock source",
)
@click.option(
    "--max-messages",
    type=int,
    help="Maximum messages to process",
)
@click.option(
    "--duration",
    type=int,
    help="Maximum runtime in seconds",
)
@click.option(
    "--legacy",
    is_flag=True,
    help="Use legacy CSV-based consumer (lsst_alert_consumer.py)",
)
@click.pass_context
def ingest(
    ctx: click.Context,
    source: str,
    topic: str | None,
    path: Path | None,
    count: int,
    max_messages: int | None,
    duration: int | None,
    legacy: bool,
) -> None:
    """Run the ingestion pipeline.

    Consumes alerts from the specified source and writes to the database.

    Use --legacy to run the original CSV-based consumer instead.
    """
    settings = ctx.obj["settings"]
    logger = get_logger(__name__)

    # Legacy mode: use original CSV-based consumer
    if legacy:
        console.print("[bold]LSST Extendedness Pipeline - Legacy Mode[/bold]")
        console.print("[yellow]Using original CSV-based consumer[/yellow]")

        # Import and run the legacy consumer
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        try:
            from lsst_alert_consumer import LSSTAlertConsumer

            kafka_config = settings.kafka.to_consumer_config()
            kafka_topic = topic or settings.kafka.topic

            consumer = LSSTAlertConsumer(  # type: ignore[no-untyped-call]
                kafka_config=kafka_config,
                base_dir=str(settings.data_dir),
            )

            console.print(f"Topic: [cyan]{kafka_topic}[/cyan]")
            console.print("Starting legacy consumer (Ctrl+C to stop)...")

            consumer.consume_alerts(  # type: ignore[no-untyped-call]
                topic=kafka_topic,
                max_messages=max_messages,
                duration_seconds=duration,
            )

            console.print("[green]Legacy ingestion complete[/green]")
        except ImportError as e:
            console.print(f"[red]Error:[/red] Could not import legacy consumer: {e}")
            console.print("Make sure lsst_alert_consumer.py is in the src/ directory")
        return

    console.print("[bold]LSST Extendedness Pipeline - Ingestion[/bold]")
    console.print(f"Source: [cyan]{source}[/cyan]")

    # Initialize storage
    db_path = settings.database_path
    storage = SQLiteStorage(db_path)
    storage.initialize()

    # Create source
    from lsst_extendedness.sources import FileSource, KafkaSource, MockSource
    from lsst_extendedness.sources.protocol import AlertSource

    alert_source: AlertSource

    if source == "mock":
        alert_source = MockSource(count=count)
        console.print(f"Generating {count} mock alerts")
    elif source == "file":
        if path is None:
            console.print("[red]Error:[/red] --path required for file source")
            return

        alert_source = FileSource(path)
        console.print(f"Reading from: {path}")
    else:
        kafka_topic = topic or settings.kafka.topic
        alert_source = KafkaSource(
            settings.kafka.to_consumer_config(),
            topic=kafka_topic,
        )
        console.print(f"Consuming from topic: [cyan]{kafka_topic}[/cyan]")

    # Connect and process
    alert_source.connect()

    from lsst_extendedness.models import IngestionRun

    run = IngestionRun(source_name=source)
    storage.write_ingestion_run(run)

    limit = max_messages or settings.ingestion.max_messages
    batch = []
    batch_size = settings.ingestion.batch_size

    try:
        with console.status("[bold green]Processing alerts...") as status:
            for alert in alert_source.fetch_alerts(limit=limit):
                batch.append(alert)
                run.alerts_ingested += 1

                if len(batch) >= batch_size:
                    storage.write_batch(batch)
                    status.update(f"Processed {run.alerts_ingested:,} alerts")
                    batch = []

            # Write remaining
            if batch:
                storage.write_batch(batch)

        run.complete()

    except Exception as e:
        run.fail(str(e))
        logger.error("Ingestion failed", error=str(e))
        console.print(f"[red]Error:[/red] {e}")

    finally:
        storage.write_ingestion_run(run)
        alert_source.close()
        storage.close()

    # Show summary
    console.print()
    console.print("[bold]Ingestion Complete[/bold]")
    console.print(f"  Alerts ingested: [green]{run.alerts_ingested:,}[/green]")
    console.print(f"  Status: [{'green' if run.is_complete else 'red'}]{run.status.value}[/]")

    if run.duration_seconds:
        rate = run.alerts_ingested / run.duration_seconds if run.duration_seconds > 0 else 0
        console.print(f"  Duration: {run.duration_seconds:.1f}s ({rate:.0f} alerts/sec)")


@main.command("backfill")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--format",
    "file_format",
    type=click.Choice(["auto", "csv", "avro"]),
    default="auto",
    help="File format (auto-detect by default)",
)
@click.option(
    "--limit",
    type=int,
    help="Maximum records to import",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be imported without writing",
)
@click.pass_context
def backfill(
    ctx: click.Context,
    path: Path,
    file_format: str,
    limit: int | None,
    dry_run: bool,
) -> None:
    """Import historical data from CSV or AVRO files.

    PATH can be a single file, directory, or glob pattern.

    Examples:

        # Import from legacy CSV files
        lsst-extendedness backfill data/processed/csv/

        # Import specific AVRO dump
        lsst-extendedness backfill dumps/alerts_20240101.avro

        # Dry run to see what would be imported
        lsst-extendedness backfill data/*.csv --dry-run
    """
    settings = ctx.obj["settings"]

    console.print("[bold]LSST Extendedness Pipeline - Backfill[/bold]")
    console.print(f"Path: [cyan]{path}[/cyan]")

    # Create file source
    from lsst_extendedness.sources import FileSource

    file_type = None if file_format == "auto" else file_format
    source = FileSource(path, file_type=file_type)
    source.connect()

    if not source._files:
        console.print("[yellow]No matching files found[/yellow]")
        return

    console.print(f"Found [green]{len(source._files)}[/green] file(s)")
    for f in source._files[:5]:
        console.print(f"  • {f.name}")
    if len(source._files) > 5:
        console.print(f"  ... and {len(source._files) - 5} more")

    if dry_run:
        console.print()
        console.print("[yellow]Dry run - counting records...[/yellow]")
        count = 0
        for _ in source.fetch_alerts(limit=limit):
            count += 1
        console.print(f"Would import [green]{count:,}[/green] alerts")
        return

    # Initialize storage
    db_path = settings.database_path
    storage = SQLiteStorage(db_path)
    storage.initialize()

    from lsst_extendedness.models import IngestionRun

    run = IngestionRun(source_name=f"backfill:{path.name}")
    storage.write_ingestion_run(run)

    batch = []
    batch_size = settings.ingestion.batch_size

    try:
        with console.status("[bold green]Importing alerts...") as status:
            for alert in source.fetch_alerts(limit=limit):
                batch.append(alert)
                run.alerts_ingested += 1

                if len(batch) >= batch_size:
                    storage.write_batch(batch)
                    status.update(f"Imported {run.alerts_ingested:,} alerts")
                    batch = []

            # Write remaining
            if batch:
                storage.write_batch(batch)

        run.complete()
        storage.write_ingestion_run(run)

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
        run.fail("User interrupted")
        storage.write_ingestion_run(run)
    except Exception as e:
        console.print(f"\n[red]Error:[/red] {e}")
        run.fail(str(e))
        storage.write_ingestion_run(run)
    finally:
        source.close()
        storage.close()

    console.print()
    console.print("[bold]Backfill Complete[/bold]")
    console.print(f"  Alerts imported: [green]{run.alerts_ingested:,}[/green]")
    console.print(f"  Status: [{'green' if run.is_complete else 'red'}]{run.status.value}[/]")


@main.command("process")
@click.option(
    "--processor",
    "-p",
    help="Specific processor to run (default: all)",
)
@click.option(
    "--window",
    "-w",
    type=int,
    default=15,
    help="Time window in days",
)
@click.option(
    "--list",
    "list_processors",
    is_flag=True,
    help="List available processors",
)
@click.option(
    "--no-save",
    is_flag=True,
    help="Don't save results to database",
)
@click.pass_context
def process(
    ctx: click.Context,
    processor: str | None,
    window: int,
    list_processors: bool,
    no_save: bool,
) -> None:
    """Run post-processing on accumulated alerts.

    Executes registered processors to analyze alert data.
    Results are stored in the processing_results table.
    """
    settings = ctx.obj["settings"]

    # Initialize storage
    db_path = settings.database_path
    if not db_path.exists():
        console.print(f"[red]Database not found:[/red] {db_path}")
        console.print("Run 'lsst-extendedness db-init' and ingest data first.")
        return

    storage = SQLiteStorage(db_path)

    from lsst_extendedness.processing import ProcessingRunner

    runner = ProcessingRunner(storage)

    # List processors if requested
    if list_processors:
        table = Table(title="Available Processors")
        table.add_column("Name", style="cyan")
        table.add_column("Version", style="green")
        table.add_column("Description")

        for info in runner.list_processors():
            table.add_row(info["name"], info["version"], info["description"])

        console.print(table)
        storage.close()
        return

    console.print("[bold]LSST Extendedness Pipeline - Processing[/bold]")
    console.print(f"Window: [cyan]{window} days[/cyan]")

    save_results = not no_save

    if processor:
        # Run specific processor
        console.print(f"Processor: [cyan]{processor}[/cyan]")

        with console.status(f"[bold green]Running {processor}..."):
            result = runner.run(
                processor,
                window_days=window,
                save_result=save_results,
            )

        if result.success and result.result is not None:
            console.print(f"[green]✓[/green] {result.result.summary}")
            console.print(f"  Records: {len(result.result.records)}")
            console.print(f"  Duration: {result.elapsed_seconds:.2f}s")
        else:
            console.print(f"[red]✗[/red] Failed: {result.error_message}")

    else:
        # Run all processors
        with console.status("[bold green]Running all processors..."):
            batch_result = runner.run_all(
                window_days=window,
                save_results=save_results,
            )

        console.print()
        console.print("[bold]Processing Results[/bold]")

        for result in batch_result.results:
            if result.success and result.result is not None:
                console.print(
                    f"  [green]✓[/green] {result.processor_name}: {result.result.summary}"
                )
            else:
                console.print(f"  [red]✗[/red] {result.processor_name}: {result.error_message}")

        console.print()
        console.print(
            f"Completed: {batch_result.success_count} succeeded, "
            f"{batch_result.failure_count} failed "
            f"({batch_result.total_elapsed_seconds:.2f}s)"
        )

    storage.close()


@main.command("query")
@click.option(
    "--today",
    "query_today",
    is_flag=True,
    help="Query today's alerts",
)
@click.option(
    "--recent",
    type=int,
    help="Query recent N days",
)
@click.option(
    "--minimoon",
    is_flag=True,
    help="Query minimoon candidates",
)
@click.option(
    "--sso",
    is_flag=True,
    help="Query SSO alerts",
)
@click.option(
    "--sql",
    help="Custom SQL query",
)
@click.option(
    "--export",
    type=click.Path(path_type=Path),
    help="Export results to file",
)
@click.option(
    "--limit",
    type=int,
    default=100,
    help="Limit results",
)
@click.pass_context
def query(
    ctx: click.Context,
    query_today: bool,
    recent: int | None,
    minimoon: bool,
    sso: bool,
    sql: str | None,
    export: Path | None,
    limit: int,
) -> None:
    """Query the alert database.

    Provides shortcuts for common queries and custom SQL support.
    """
    settings = ctx.obj["settings"]

    db_path = settings.database_path
    if not db_path.exists():
        console.print(f"[red]Database not found:[/red] {db_path}")
        return

    storage = SQLiteStorage(db_path)

    from lsst_extendedness.query import shortcuts

    # Determine query
    if sql:
        df = shortcuts.custom(sql, storage=storage)
        title = "Custom Query"
    elif query_today:
        df = shortcuts.today(storage=storage)
        title = "Today's Alerts"
    elif recent:
        df = shortcuts.recent(days=recent, storage=storage)
        title = f"Last {recent} Days"
    elif minimoon:
        df = shortcuts.minimoon_candidates(storage=storage)
        title = "Minimoon Candidates"
    elif sso:
        df = shortcuts.sso_alerts(storage=storage)
        title = "SSO Alerts"
    else:
        # Default: show stats
        stats = shortcuts.stats(storage=storage)
        console.print("[bold]Database Summary[/bold]")
        for key, value in stats.items():
            if isinstance(value, dict):
                console.print(f"  {key}:")
                for k, v in value.items():
                    console.print(f"    {k}: {v}")
            else:
                console.print(f"  {key}: {value}")
        storage.close()
        return

    # Apply limit
    if len(df) > limit:
        df = df.head(limit)
        console.print(f"[yellow]Showing first {limit} of {len(df)} results[/yellow]")

    # Export or display
    if export:
        from lsst_extendedness.query.export import ExportFormat, export_dataframe

        fmt_str = export.suffix.lstrip(".") or "csv"
        # Validate format
        if fmt_str not in ("csv", "parquet", "json", "excel"):
            console.print(f"[red]Unsupported format:[/red] {fmt_str}")
            storage.close()
            return
        fmt: ExportFormat = fmt_str  # type: ignore[assignment]
        export_dataframe(df, export, format=fmt)
        console.print(f"[green]Exported to:[/green] {export}")
    else:
        console.print(f"[bold]{title}[/bold] ({len(df)} rows)")
        console.print()

        # Display as table
        if len(df) > 0:
            table = Table(show_lines=True)
            for col in df.columns[:10]:  # Limit columns
                table.add_column(str(col), overflow="fold")

            for _, row in df.head(20).iterrows():
                table.add_row(*[str(v)[:50] for v in row.values[:10]])

            console.print(table)

            if len(df) > 20:
                console.print(f"[dim]... and {len(df) - 20} more rows[/dim]")

    storage.close()


@main.command("export")
@click.option(
    "--type",
    "export_type",
    type=click.Choice(["today", "recent", "minimoon", "sso", "results"]),
    default="today",
    help="Type of export",
)
@click.option(
    "--days",
    type=int,
    default=7,
    help="Days for recent export",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["csv", "parquet", "json"]),
    default="csv",
    help="Output format",
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    default="exports",
    help="Output directory",
)
@click.pass_context
def export_cmd(
    ctx: click.Context,
    export_type: str,
    days: int,
    fmt: str,
    output_dir: Path,
) -> None:
    """Export data to files."""
    settings = ctx.obj["settings"]

    db_path = settings.database_path
    if not db_path.exists():
        console.print(f"[red]Database not found:[/red] {db_path}")
        return

    storage = SQLiteStorage(db_path)

    from lsst_extendedness.query.export import DataExporter, ExportFormat

    # Validate format
    if fmt not in ("csv", "parquet", "json", "excel"):
        console.print(f"[red]Unsupported format:[/red] {fmt}")
        storage.close()
        return
    export_fmt: ExportFormat = fmt  # type: ignore[assignment]
    exporter = DataExporter(storage, output_dir, default_format=export_fmt)

    console.print(f"[bold]Exporting {export_type}...[/bold]")

    if export_type == "today":
        path = exporter.today()
    elif export_type == "recent":
        path = exporter.recent(days=days)
    elif export_type == "minimoon":
        path = exporter.minimoon_candidates()
    elif export_type == "sso":
        path = exporter.sso_summary()
    elif export_type == "results":
        path = exporter.processing_results()
    else:
        console.print(f"[red]Unknown export type:[/red] {export_type}")
        storage.close()
        return

    console.print(f"[green]Exported to:[/green] {path}")
    storage.close()


@main.command("health-check")
@click.pass_context
def health_check(ctx: click.Context) -> None:
    """Run system health check."""
    settings = ctx.obj["settings"]

    console.print("[bold]System Health Check[/bold]")
    console.print()

    # Check Python
    import sys

    console.print(f"Python: [green]{sys.version.split()[0]}[/green]")

    # Check database
    db_path = settings.database_path
    if db_path.exists():
        storage = SQLiteStorage(db_path)
        stats = storage.get_stats()
        count = stats.get("alerts_raw_count", 0)
        console.print(f"Database: [green]OK[/green] ({count:,} alerts)")
        storage.close()
    else:
        console.print("Database: [yellow]Not initialized[/yellow]")

    # Check Kafka (optional)
    try:
        import confluent_kafka  # noqa: F401

        console.print("Kafka client: [green]Installed[/green]")
    except ImportError:
        console.print("Kafka client: [yellow]Not installed[/yellow]")

    # Check pandas
    try:
        import pandas

        console.print(f"Pandas: [green]{pandas.__version__}[/green]")
    except ImportError:
        console.print("Pandas: [red]Not installed[/red]")

    # Check numpy BLAS
    try:
        import numpy as np

        console.print(f"NumPy: [green]{np.__version__}[/green]")
    except ImportError:
        console.print("NumPy: [red]Not installed[/red]")

    console.print()
    console.print("[green]Health check complete[/green]")


# Entry points for scripts
def ingest_cli() -> None:
    """Entry point for lsst-ingest command."""
    main(["ingest"])


def query_cli() -> None:
    """Entry point for lsst-query command."""
    main(["query"])


def process_cli() -> None:
    """Entry point for lsst-process command."""
    main(["process"])


if __name__ == "__main__":
    main()
