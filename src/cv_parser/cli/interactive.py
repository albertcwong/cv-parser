"""Interactive CLI: select file, parse, verify, retry with feedback, output."""

from pathlib import Path

from cv_parser.cli.display import format_result, format_usage
from cv_parser.cli.file_browser import browse_and_select
from cv_parser.combiner import combine_to_flat, load_from_json
from cv_parser.config import get_max_retries, get_retry_on_validation_error, get_temp_dir, get_threads, get_two_pass, get_use_extracted_text, load_config, resolve, save_config
from cv_parser.export import export_csv, export_json
from cv_parser.line_parser import parse_cv_from_lines
from cv_parser.providers import get_provider
from cv_parser.schemas import CVParseResult, Usage


MIME = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
}


def run_menu(
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    retry_on_validation_error: bool | None = None,
    two_pass: bool | None = None,
    use_extracted_text: bool | None = None,
) -> None:
    """Show top-level menu and dispatch to parse, export, or settings. Loops until Quit."""
    while True:
        prov, mod, key, mod_ext, mod_cls = resolve(provider=provider, model=model, api_key=api_key)
        retry = retry_on_validation_error if retry_on_validation_error is not None else get_retry_on_validation_error()
        two = two_pass if two_pass is not None else get_two_pass()
        use_ext = use_extracted_text if use_extracted_text is not None else get_use_extracted_text()
        max_ret = get_max_retries()
        try:
            import questionary
            choice = questionary.select(
                "What would you like to do?",
                choices=[
                    "Parse one CV — interactive, verify before saving",
                    "Parse many CVs — queue files, process in background",
                    "Job status — monitor parse queue and progress",
                    "Export parsed CV — select multiple JSON outputs, choose export location",
                    "Settings — provider, model, API key, threads, two-pass, retry",
                    "Quit",
                ],
            ).ask()
        except ImportError:
            print("1. Parse one CV  2. Parse many CVs  3. Job status  4. Export  5. Settings  6. Quit")
            c = input("Choice: ").strip()
            choice = (
                "Parse one CV" if c == "1"
                else "Parse many CVs" if c == "2"
                else "Job status" if c == "3"
                else "Export" if c == "4"
                else "Settings" if c == "5"
                else "Quit" if c == "6" else None
            )

        if not choice or "Quit" in choice:
            return
        if "Settings" in choice:
            run_settings_menu()
            continue
        if "Job status" in choice:
            run_job_status_menu(prov, mod, key, retry, two, max_ret)
            continue
        if "Export" in choice:
            run_export_interactive()
            continue
        if "Parse many CVs" in choice:
            run_async_parse(prov, mod, key, retry, two, max_ret, use_ext, mod_ext, mod_cls)
            continue
        run_interactive(
            provider=prov,
            model=mod,
            api_key=key,
            model_extraction=mod_ext,
            model_classification=mod_cls,
            retry_on_validation_error=retry,
            two_pass=two,
            max_retries=max_ret,
            use_extracted_text=use_ext,
        )


def run_async_parse(
    provider: str,
    model: str | None,
    api_key: str | None,
    retry_on_validation_error: bool,
    two_pass: bool,
    max_retries: int = 1,
    use_extracted_text: bool = False,
    model_extraction: str | None = None,
    model_classification: str | None = None,
) -> None:
    """Queue files for async parsing. Two-pass default."""
    paths = browse_and_select(
        Path.cwd(),
        extensions=(".pdf", ".docx", ".doc"),
        title="Select CV files to parse",
    )
    if not paths:
        return

    try:
        import questionary
        out_dir = questionary.path("Output directory:", default="output").ask()
    except ImportError:
        out_dir = input("Output directory [output]: ").strip() or "output"
    out_dir = Path(out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        import questionary
        layout = questionary.select(
            "Output layout:",
            choices=["Individual (one file per input)", "Combined (one file)"],
        ).ask()
    except ImportError:
        layout = "Individual" if input("Individual or combined? (i/c): ").strip().lower().startswith("i") else "Combined"

    try:
        import questionary
        fmt = questionary.select("Output format:", choices=["JSON", "CSV"]).ask()
    except ImportError:
        fmt = "JSON" if input("Format (json/csv): ").strip().lower().startswith("j") else "CSV"

    from cv_parser.jobs import get_queue
    q = get_queue()
    q.configure(
        output_dir=out_dir,
        provider=provider,
        model=model,
        api_key=api_key,
        retry_on_validation_error=retry_on_validation_error,
        max_retries=max_retries,
        two_pass=two_pass,
        layout=layout or "Individual",
        format=fmt or "JSON",
        temp_dir=get_temp_dir(),
        use_extracted_text=use_extracted_text,
        model_extraction=model_extraction,
        model_classification=model_classification,
    )
    jobs = q.enqueue(paths)
    print(f"Queued {len(jobs)} file(s). Use Job status to monitor.")


def run_job_status_menu(
    provider: str,
    model: str | None,
    api_key: str | None,
    retry_on_validation_error: bool,
    two_pass: bool,
    max_retries: int = 1,
) -> None:
    """Monitor job queue: queued, in-progress (with %), done, failed. Auto-refreshes every 2s."""
    import select
    import sys
    import time

    from cv_parser.jobs import get_queue

    def _render() -> str:
        from cv_parser.jobs import JobStatus, _format_dt, _format_runtime

        q = get_queue()
        all_jobs = q.get_all()
        if not all_jobs:
            return "No jobs."

        def _phase(j) -> str:
            if j.status == JobStatus.QUEUED:
                return "queued"
            if j.status == JobStatus.IN_PROGRESS:
                return f"{j.phase or 'processing'} {int(j.progress)}%" if j.phase else f"{int(j.progress)}%"
            if j.status == JobStatus.DONE:
                return "done"
            err = (j.error or "")[:30]
            return f"failed: {err}..." if j.error and len(j.error) > 30 else f"failed: {err}" if err else "failed"

        def _start(j) -> str:
            return _format_dt(j.start_time) if j.start_time else ""

        def _runtime(j) -> str:
            return _format_runtime(sec) if (sec := j.runtime_seconds) is not None else ""

        rows = [(j.name, _phase(j), _start(j), _runtime(j)) for j in all_jobs]
        w_name = max(len("filename"), max(len(r[0]) for r in rows), 20)
        w_phase = max(len("phase"), max(len(r[1]) for r in rows), 12)
        w_start = max(len("start time"), max(len(r[2]) for r in rows), 19)
        w_runtime = max(len("runtime"), max(len(r[3]) for r in rows), 8)

        sep = "  "
        header = f"{'filename':<{w_name}}{sep}{'phase':<{w_phase}}{sep}{'start time':<{w_start}}{sep}{'runtime':<{w_runtime}}"
        div = "-" * len(header)
        lines = [header, div]
        for name, phase, start, runtime in rows:
            lines.append(f"{name:<{w_name}}{sep}{phase:<{w_phase}}{sep}{start:<{w_start}}{sep}{runtime:<{w_runtime}}")
        return "\n".join(lines)

    interval = 2
    while True:
        try:
            print("\033[2J\033[H", end="")  # clear screen, cursor home
        except Exception:
            print("\n" * 2)
        print(_render())
        print(f"\nPress Enter for Back (auto-refresh every {interval}s)")
        try:
            r, _, _ = select.select([sys.stdin], [], [], interval)
            if r:
                sys.stdin.readline()
                return
        except (ValueError, OSError):
            if sys.platform == "win32":
                for _ in range(interval * 10):
                    time.sleep(0.1)
                    try:
                        import msvcrt
                        if msvcrt.kbhit() and msvcrt.getch() in (b"\r", b"\n"):
                            return
                    except ImportError:
                        pass
            else:
                time.sleep(interval)


def run_export_interactive() -> None:
    """Browse JSON files, choose format, export."""
    paths = browse_and_select(
        Path.cwd(),
        extensions=(".json",),
        title="Select JSON files",
    )
    if not paths:
        return

    try:
        results = load_from_json(paths)
    except Exception as e:
        print(f"Error loading: {e}")
        return

    try:
        import questionary
        fmt = questionary.select(
            "Export format:",
            choices=["JSON", "CSV"],
        ).ask()
    except ImportError:
        fmt = input("Format (json/csv): ").strip().lower() or "csv"
        fmt = "JSON" if fmt.startswith("j") else "CSV"

    default_name = "combined.csv" if fmt == "CSV" else "combined.json"
    try:
        import questionary
        out = questionary.path(
            f"Output file or directory (dir → {default_name} inside):",
            default="",
        ).ask()
    except ImportError:
        out = input(f"Output file or directory (dir → {default_name} inside): ").strip()

    out_path = Path(out).expanduser().resolve() if out else None
    if out_path and (out_path.is_dir() or (not out_path.suffix and not out_path.exists())):
        out_path = out_path / default_name
    if fmt == "CSV":
        rows = combine_to_flat(results)
        if out_path:
            export_csv(rows, out_path)
        else:
            export_csv(rows, None)
    else:
        if out_path:
            export_json(results, out_path)
        else:
            export_json(results, None)
    if out_path:
        print(f"Wrote {out_path}")


def run_settings_menu() -> None:
    """Edit and persist provider, model, api_key, threads, two_pass, retry."""
    while True:
        cfg = load_config()
        prov = cfg.get("provider") or "openai"
        mod = cfg.get("model") or ""
        mod_ext = cfg.get("model_extraction") or ""
        mod_cls = cfg.get("model_classification") or ""
        key = cfg.get("api_key") or ""
        threads = get_threads()
        two = get_two_pass()
        retry = get_retry_on_validation_error()
        max_ret = get_max_retries()
        use_ext = get_use_extracted_text()

        try:
            import questionary
            choice = questionary.select(
                "Settings",
                choices=[
                    f"Provider: {prov}",
                    f"Model: {mod or '(default)'}",
                    f"Model extraction: {mod_ext or '(default)'}",
                    f"Model classification: {mod_cls or '(default)'}",
                    f"API key: {'***' if key else '(not set)'}",
                    f"Parse threads: {threads}",
                    f"Two-pass extraction: {'on' if two else 'off'}",
                    f"Use extracted text (not original file): {'on' if use_ext else 'off'}",
                    f"Retry on validation error: {'on' if retry else 'off'}",
                    f"Max retries: {max_ret}",
                    "Back",
                ],
            ).ask()
        except ImportError:
            print("1. Provider  2. Model  3. API key  4. Threads  5. Two-pass  6. Use extracted text  7. Retry  8. Max retries  9. Back")
            c = input("Choice: ").strip()
            choice = (
                f"Provider: {prov}" if c == "1" else f"Model: {mod or '(default)'}" if c == "2"
                else f"API key: {'***' if key else '(not set)'}" if c == "3"
                else f"Parse threads: {threads}" if c == "4"
                else f"Two-pass extraction: {'on' if two else 'off'}" if c == "5"
                else f"Use extracted text (not original file): {'on' if use_ext else 'off'}" if c == "6"
                else f"Retry on validation error: {'on' if retry else 'off'}" if c == "7"
                else f"Max retries: {max_ret}" if c == "8"
                else "Back"
            )

        if not choice or "Back" in choice:
            return

        if "Provider" in choice:
            try:
                import questionary
                new = questionary.select("Provider:", choices=["openai", "anthropic", "gemini"], default=prov).ask()
            except ImportError:
                new = input(f"Provider (openai/anthropic/gemini) [{prov}]: ").strip() or prov
            if new:
                save_config(provider=new)
                print(f"Saved provider: {new}")
        elif choice == "Model: " + (mod or "(default)"):
            try:
                import questionary
                new = questionary.text("Model (blank = provider default):", default=mod).ask() or ""
            except ImportError:
                new = input(f"Model [{mod}]: ").strip()
            save_config(model=new or None)
            print(f"Saved model: {new or '(default)'}")
        elif "Model extraction" in choice:
            try:
                import questionary
                new = questionary.text("Model (blank = use default):", default=mod_ext).ask() or ""
            except ImportError:
                new = input(f"Model extraction [{mod_ext}]: ").strip()
            save_config(model_extraction=new or None)
            print(f"Saved model extraction: {new or '(default)'}")
        elif "Model classification" in choice:
            try:
                import questionary
                new = questionary.text("Model (blank = use default):", default=mod_cls).ask() or ""
            except ImportError:
                new = input(f"Model classification [{mod_cls}]: ").strip()
            save_config(model_classification=new or None)
            print(f"Saved model classification: {new or '(default)'}")
        elif "API key" in choice:
            try:
                import questionary
                new = questionary.password("API key (blank to clear):").ask() or ""
            except ImportError:
                import getpass
                new = getpass.getpass("API key (blank to clear): ") or ""
            save_config(api_key=new)
            print("Saved API key" if new else "Cleared API key")
        elif "threads" in choice.lower():
            try:
                import questionary
                new = questionary.text("Parse threads (1-16):", default=str(threads)).ask()
            except ImportError:
                new = input(f"Parse threads (1-16) [{threads}]: ").strip() or str(threads)
            try:
                n = max(1, min(16, int(new)))
                save_config(threads=n)
                print(f"Saved threads: {n} (takes effect for new parse batches)")
            except ValueError:
                print("Invalid number")
        elif "Two-pass" in choice:
            save_config(two_pass=not two)
            print(f"Saved two-pass: {'on' if not two else 'off'}")
        elif "Use extracted text" in choice:
            save_config(use_extracted_text=not use_ext)
            print(f"Saved use extracted text: {'on' if not use_ext else 'off'}")
        elif "Retry" in choice and "Max" not in choice:
            save_config(retry_on_validation_error=not retry)
            print(f"Saved retry on validation error: {'on' if not retry else 'off'}")
        elif "Max retries" in choice:
            try:
                import questionary
                new = questionary.text("Max retries (0-5):", default=str(max_ret)).ask()
            except ImportError:
                new = input(f"Max retries (0-5) [{max_ret}]: ").strip() or str(max_ret)
            try:
                n = max(0, min(5, int(new)))
                save_config(max_retries=n)
                print(f"Saved max retries: {n}")
            except ValueError:
                print("Invalid number")


def run_interactive(
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    model_extraction: str | None = None,
    model_classification: str | None = None,
    retry_on_validation_error: bool = True,
    two_pass: bool = False,
    max_retries: int | None = None,
    use_extracted_text: bool = False,
) -> None:
    """Run interactive parse (single file) or batch parse (multiple files)."""
    paths = browse_and_select(
        Path.cwd(),
        extensions=(".pdf", ".docx", ".doc"),
        title="Select CV files",
    )
    if not paths:
        return

    if len(paths) > 1:
        _run_batch_parse(paths, provider, model, api_key, retry_on_validation_error, two_pass, max_retries or 1, use_extracted_text, model_extraction, model_classification)
        return

    path = paths[0]
    print(f"Parsing {path.name}...", flush=True)
    try:
        result = parse_cv_from_lines(path, provider=provider, model=model, api_key=api_key)
    except Exception as e:
        print(f"Error: {e}")
        return
    print(format_result(result))
    print(flush=True)
    if _prompt_accept():
        _output_result(result, path)


def _parse_two_pass_with_display(prov_extraction, prov_classification, document, mime, **kwargs):
    """Two-pass parse with extraction and classification phases."""
    try:
        from rich.console import Console
        console = Console()
    except ImportError:
        console = None

    def on_chunk(chunk: str) -> None:
        print(chunk, end="", flush=True)

    if console:
        console.print("\n[bold dim]Extracting all items...[/bold dim]")
        console.print("[dim]--- Streaming ---[/dim]")
    else:
        print("\nExtracting all items...\n--- Streaming ---", flush=True)

    def on_classification_start():
        print()  # newline after extraction stream
        if console:
            console.print("[bold dim]Classifying items...[/bold dim]")
            console.print("[dim]--- Streaming ---[/dim]")
        else:
            print("Classifying items...\n--- Streaming ---", flush=True)

    result, usage = parse_two_pass(
        prov_extraction,
        prov_classification,
        document,
        mime,
        stream_callback=on_chunk,
        on_classification_start=on_classification_start,
        **kwargs,
    )

    print()  # newline after stream
    if console:
        console.print(f"[green]✓[/green] Done.\n")
    else:
        print("Done.\n", flush=True)
    return result, usage


def _parse_with_stream(prov, document, mime, msg, **kwargs):
    """Parse with streaming display and return (result, usage)."""
    try:
        from rich.console import Console
        console = Console()
    except ImportError:
        console = None

    def on_chunk(chunk: str) -> None:
        print(chunk, end="", flush=True)

    if console:
        console.print(f"\n[bold dim]{msg}[/bold dim]")
        console.print("[dim]--- Streaming ---[/dim]")
    else:
        print(f"\n{msg}\n--- Streaming ---", flush=True)

    result, usage = prov.parse(
        document,
        mime,
        stream_callback=on_chunk,
        **kwargs,
    )

    print()  # newline after stream
    if console:
        console.print(f"[green]✓[/green] Done.\n")
    else:
        print("Done.\n", flush=True)
    return result, usage


def _run_batch_parse(
    paths: list[Path],
    provider,
    model,
    api_key,
    retry_on_validation_error: bool,
    two_pass: bool,
    max_retries: int = 1,
    use_extracted_text: bool = False,
    model_extraction: str | None = None,
    model_classification: str | None = None,
) -> None:
    """Batch parse: no verify loop, prompt output dir, individual/combined, JSON/CSV."""
    results = []
    for p in paths:
        print(f"Parsing {p.name}...", flush=True)
        try:
            r = parse_cv_from_lines(p, provider=provider, model=model, api_key=api_key)
            results.append((p, r))
        except Exception as e:
            print(f"  Error: {e}", flush=True)
    print(f"Parsed {len(results)} file(s).", flush=True)

    try:
        import questionary
        out_dir = questionary.path("Output directory:", default="output").ask()
    except ImportError:
        out_dir = input("Output directory [output]: ").strip() or "output"
    out_dir = Path(out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        import questionary
        layout = questionary.select(
            "Output layout:",
            choices=["Individual (one file per input)", "Combined (one file)"],
        ).ask()
    except ImportError:
        layout = "Individual" if input("Individual or combined? (i/c): ").strip().lower().startswith("i") else "Combined"

    try:
        import questionary
        fmt = questionary.select("Output format:", choices=["JSON", "CSV"]).ask()
    except ImportError:
        fmt = "JSON" if input("Format (json/csv): ").strip().lower().startswith("j") else "CSV"

    if layout and "Combined" in layout:
        all_results = [r for _, r in results]
        if fmt == "CSV":
            rows = combine_to_flat(all_results)
            export_csv(rows, out_dir / "combined.csv")
        else:
            export_json(all_results, out_dir / "combined.json")
        print(f"Wrote {out_dir / ('combined.csv' if fmt == 'CSV' else 'combined.json')}")
    else:
        for p, result in results:
            stem = p.stem
            if fmt == "CSV":
                rows = combine_to_flat([result])
                export_csv(rows, out_dir / f"{stem}.csv")
            else:
                export_json(result, out_dir / f"{stem}.json")
        print(f"Wrote {len(results)} file(s) to {out_dir}")


def _select_file() -> Path | None:
    """Select file via questionary or simple input."""
    try:
        import questionary
        path = questionary.path(
            "Path to CV (PDF or docx):",
            default="",
        ).ask()
    except ImportError:
        path = input("Path to CV (PDF or docx): ").strip()

    if not path:
        return None
    p = Path(path).expanduser().resolve()
    if not p.exists():
        print(f"File not found: {p}")
        return None
    if p.suffix.lower() not in (".pdf", ".docx", ".doc"):
        print("Use .pdf or .docx")
        return None
    return p


def _prompt_accept() -> bool:
    """Return True if user accepts (satisfied), False to retry."""
    print("\n--- Satisfied with result? ---", flush=True)
    try:
        import questionary
        choice = questionary.select(
            "Accept or Retry?",
            choices=["Accept (a)", "Retry (r)"],
        ).ask()
        return choice == "Accept (a)" if choice else False
    except ImportError:
        r = input("Accept (a) / Retry (r): ").strip().lower()
        return r.startswith("a")


def _prompt_feedback() -> str:
    """Get optional user feedback for retry."""
    try:
        import questionary
        return questionary.text(
            "Optional comments for the LLM:",
            default="",
        ).ask() or ""
    except ImportError:
        return input("Optional comments: ").strip()


def _prompt_retry() -> bool:
    """Ask user if they want to retry after error."""
    r = input("Retry? (y/n): ").strip().lower()
    return r.startswith("y")


def _output_result(result: CVParseResult, path: Path | None = None) -> None:
    """Prompt for format and output path, write JSON or CSV."""
    try:
        import questionary
        fmt = questionary.select("Output format:", choices=["JSON", "CSV"]).ask()
    except ImportError:
        fmt = "JSON" if input("Format (json/csv): ").strip().lower().startswith("j") else "CSV"

    from datetime import datetime
    ts = datetime.now().strftime("%Y-%m-%d_%H_%M_%S")
    stem = path.stem if path else "output"
    filename = f"parsed_{stem}_{ts}.csv" if fmt == "CSV" else f"parsed_{stem}_{ts}.json"
    default_path = Path("output") / filename
    try:
        import questionary
        out = questionary.path(
            f"Output file, directory, or Enter for {default_path}:",
            default=str(default_path),
        ).ask()
    except ImportError:
        out = input(f"Output file, directory, or Enter for {default_path}: ").strip() or str(default_path)

    if out and out.lower() in ("print", "-", "stdout"):
        out_path = None
    elif out:
        out_path = Path(out).expanduser().resolve()
        if out_path.is_dir() or (not out_path.suffix and not out_path.exists()):
            out_path = out_path / filename
    else:
        out_path = Path.cwd() / default_path
    if fmt == "CSV":
        rows = combine_to_flat([result])
        export_csv(rows, out_path)
    else:
        if out_path:
            export_json(result, out_path)
        else:
            export_json(result, None)
    if out_path:
        print(f"Wrote {out_path}")
