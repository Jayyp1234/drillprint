"""drillprint CLI — library / bench / demo entry points (A13)."""

from __future__ import annotations

from pathlib import Path

import typer

app = typer.Typer(help="DrillPrint — spectral fingerprinting for drilling dysfunction")
library_app = typer.Typer()
bench_app = typer.Typer()
app.add_typer(library_app, name="library")
app.add_typer(bench_app, name="bench")


@library_app.command("build")
def library_build(
    config: Path = typer.Option(Path("config/well01.yaml"), "--config"),
    db: Path = typer.Option(Path("data/library.db"), "--db"),
    version: str = typer.Option("v1", "--version"),
    subset: int | None = typer.Option(None, "--subset"),
):
    """Build a synthetic fingerprint library (M3)."""
    from synth.build_library import build
    import json
    db.parent.mkdir(parents=True, exist_ok=True)
    report = build(db, version, subset)
    typer.echo(json.dumps(report, indent=2))


@bench_app.command("run")
def bench_run(
    library: str = typer.Option("v1", "--library"),
    db: Path = typer.Option(Path("data/library.db"), "--db"),
    full: bool = typer.Option(False, "--full"),
    smoke: bool = typer.Option(False, "--smoke"),
    out: Path = typer.Option(Path("bench/report.json"), "--out"),
):
    """Run the §14 / A19 benchmark protocol (M5)."""
    from bench.run import run_protocol
    import json
    if full:
        snr_levels, n_runs, segment_s, include_ss = [20.0, 10.0, 3.0, 0.0], 10, 600.0, True
    else:
        snr_levels, n_runs, segment_s, include_ss = [10.0], 2, 45.0, False
    report = run_protocol(db, library, snr_levels, n_runs, segment_s, include_ss)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    typer.echo(f"report -> {out}")


@app.command("demo")
def demo(db: Path = typer.Option(Path("data/library.db"), "--db")):
    """Boot API + committed frontend_dist (M6 dual-serve)."""
    import uvicorn
    from api.main import create_app
    typer.echo("DRILLPRINT → http://127.0.0.1:8000  (Monitor + /docs)")
    uvicorn.run(create_app(db), host="127.0.0.1", port=8000)


if __name__ == "__main__":
    app()
