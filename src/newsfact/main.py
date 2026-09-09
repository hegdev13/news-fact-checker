"""CLI entrypoint for the multi-agent pipeline.

Claim mode (v2):
    python -m newsfact.main "A claim to check" ["another claim" ...]
    python -m newsfact.main --file path/to/claims.txt
    python -m newsfact.main --demo                 # bundled sample claims, offline
    python -m newsfact.main --demo --plain         # no live region (pipe-friendly)

Article mode (v2.1) — submit a whole article; the Claim Extractor finds the
source outlet and pulls out the checkable claim, then the normal pipeline runs:
    python -m newsfact.main --article path/to/article.txt
    python -m newsfact.main --article - --article-url https://outlet.example/story   # article on stdin
    python -m newsfact.main --demo --article                                         # bundled sample article

The run streams a live terminal dashboard (agents, shared blackboard, event
stream) for each news item, then prints the merged report and a recap. Every
event is also written to the `audit_log` table in the shared store.

Without ANTHROPIC_API_KEY set (or with --demo) it runs fully offline using the
scripted fixtures in newsfact.demo.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from newsfact.agents.cross_checker import AnthropicLLMClient
from newsfact.config import load_settings
from newsfact.demo import FakeGdeltClient, FakeLLMClient
from newsfact.graph import run_article_pipeline, run_pipeline
from newsfact.memory.store import BlackboardStore, claim_id
from newsfact.observability.console import ConsoleReporter, render_report_panel
from newsfact.observability.events import AuditLogReporter, MultiReporter
from newsfact.tools.bias_table import BiasTable
from newsfact.tools.gdelt import GdeltClient

_RESOURCES = Path(__file__).parent / "resources"
_SAMPLE_CLAIMS = _RESOURCES / "sample_claims.txt"
_SAMPLE_ARTICLE = _RESOURCES / "sample_article.txt"
_ARTICLE_SAMPLE_SENTINEL = "\x00demo-sample-article\x00"


def _read_claims_file(path: Path) -> list[str]:
    claims: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            claims.append(line)
    return claims


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="newsfact", description="Multi-agent news fact-checker (v2.1)")
    p.add_argument("claims", nargs="*", help="one or more claims/headlines to check (claim mode)")
    p.add_argument("--file", type=Path, help="file with one claim per line (# comments allowed)")
    p.add_argument("--article", nargs="?", const=_ARTICLE_SAMPLE_SENTINEL, metavar="PATH",
                   help="path to an article file to check ('-' = stdin; bare flag = bundled sample)")
    p.add_argument("--article-text", metavar="TEXT", help="inline article text to check (alternative to --article)")
    p.add_argument("--article-url", metavar="URL", help="URL the submitted article was published at (helps source ID)")
    p.add_argument("--demo", action="store_true", help="offline run using bundled samples + fixtures")
    p.add_argument("--plain", action="store_true", help="disable the live region; print a flat event trace")
    p.add_argument("--no-cache", action="store_true", help="re-run even if a report is already cached (claim mode)")
    p.add_argument("--keep-db", action="store_true", help="(demo) keep the demo DB instead of starting fresh")
    p.add_argument("--json", action="store_true", help="also print a machine-readable JSON summary at the end")
    return p.parse_args(argv)


def _resolve_article(args: argparse.Namespace, console: Console) -> str | None:
    if args.article_text:
        return args.article_text
    if args.article is None:
        return None
    if args.article == _ARTICLE_SAMPLE_SENTINEL:
        return _SAMPLE_ARTICLE.read_text(encoding="utf-8")
    if args.article == "-":
        return sys.stdin.read()
    path = Path(args.article)
    if not path.is_file():
        console.print(f"[red]--article: no such file:[/] {path}")
        raise SystemExit(1)
    return path.read_text(encoding="utf-8")


def _resolve_claims(args: argparse.Namespace) -> list[str]:
    if args.file:
        return _read_claims_file(args.file)
    if args.claims:
        return args.claims if len(args.claims) > 1 else [args.claims[0]]
    if args.demo:
        return _read_claims_file(_SAMPLE_CLAIMS)
    return []


def _make_clients(demo_mode: bool, settings, console: Console):
    if demo_mode:
        reason = "--demo flag" if settings.anthropic_api_key else "ANTHROPIC_API_KEY not set"
        console.print(
            f"[bold yellow]DEMO MODE[/] ({reason}) — offline fixtures for GDELT and Claude. "
            "Every agent runs; nothing hits the network.\n"
        )
        return FakeGdeltClient(), FakeLLMClient()
    console.print("[green]LIVE MODE[/] — real GDELT + Anthropic clients.\n")
    return GdeltClient(settings.gdelt_api_base), AnthropicLLMClient(settings.anthropic_api_key, settings.model)


def _result_row(store: BlackboardStore, cid: str, label_hint: str, cached: bool) -> dict:
    report = store.get_report(cid)
    verdict = store.get_verdict(cid)
    return {
        "claim": label_hint,
        "cached": cached,
        "label": report.verdict_label if report else (verdict.label if verdict else "unverifiable"),
        "confidence": report.verdict_confidence if report else (verdict.confidence if verdict else 0.0),
        "headline": report.headline if report else "(no report)",
        "body_md": report.body_md if report else "",
    }


def cli() -> None:
    args = _parse_args(sys.argv[1:])
    console = Console()
    settings = load_settings()

    article_text = _resolve_article(args, console)
    article_mode = article_text is not None
    claims = [] if article_mode else _resolve_claims(args)

    if article_mode and (args.claims or args.file):
        console.print("[yellow]note:[/] --article given; ignoring positional claims / --file.")
    if not article_mode and not claims:
        console.print("[red]Nothing to check.[/] Pass a claim, --file, --article, or --demo.")
        raise SystemExit(1)

    demo_mode = args.demo or not settings.anthropic_api_key
    db_path = Path("data/newsfact-demo.db") if demo_mode else Path(settings.db_path)
    if demo_mode and not args.keep_db and db_path.exists():
        db_path.unlink()

    gdelt_client, llm_client = _make_clients(demo_mode, settings, console)

    store = BlackboardStore(db_path)
    bias_table = BiasTable.load(settings.bias_table_path)
    console_reporter = ConsoleReporter(console, plain=args.plain)
    console_reporter.set_total(1 if article_mode else len(claims))
    reporter = MultiReporter([console_reporter, AuditLogReporter(store)])
    store.set_reporter(reporter)

    results: list[dict] = []
    with console_reporter:
        if article_mode:
            state = run_article_pipeline(
                article_text, store, gdelt_client, llm_client, bias_table, reporter, url=args.article_url,
            )
            cid = state["claim_id"]
            row = _result_row(store, cid, state.get("claim_text", "(submitted article)"), cached=False)
            row["from_article"] = True
            results.append(row)
        else:
            for claim in claims:
                cid = claim_id(claim)
                cached = None if args.no_cache else store.get_report(cid)
                if cached is not None:
                    console.print(f"[dim]cache hit — {claim!r} already checked; showing stored report[/]")
                    results.append({
                        "claim": claim, "cached": True,
                        "label": cached.verdict_label, "confidence": cached.verdict_confidence,
                        "headline": cached.headline, "body_md": cached.body_md,
                    })
                    continue
                run_pipeline(claim, store, gdelt_client, llm_client, bias_table, reporter)
                results.append(_result_row(store, cid, claim, cached=False))

    _print_recap(console, results, db_path)
    if args.json:
        console.print_json(json.dumps({"results": [
            {k: v for k, v in r.items() if k != "body_md"} for r in results
        ]}))


def _print_recap(console: Console, results: list[dict], db_path: Path) -> None:
    console.rule("[bold]Reports")
    for r in results:
        console.print(render_report_panel(r["headline"], r["label"], float(r["confidence"]), r["body_md"] or "_no body_"))
        console.print()

    table = Table(title="Run recap", header_style="bold")
    table.add_column("#", width=3)
    table.add_column("Verdict")
    table.add_column("Conf.", justify="right")
    table.add_column("Claim", overflow="fold")
    style = {"corroborated": "green", "disputed": "yellow", "unverifiable": "red"}
    for i, r in enumerate(results, 1):
        tag = " [dim](cached)[/]" if r["cached"] else (" [dim](from article)[/]" if r.get("from_article") else "")
        table.add_row(
            str(i),
            f"[{style.get(r['label'], 'white')}]{r['label']}[/]" + tag,
            f"{float(r['confidence']):.0%}",
            r["claim"],
        )
    console.print(table)
    console.print(f"[dim]shared blackboard + audit log: {db_path}[/]")


if __name__ == "__main__":
    cli()
