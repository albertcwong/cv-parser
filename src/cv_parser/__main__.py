"""CLI entrypoint."""

import argparse
import logging
import os
import sys
from pathlib import Path

from cv_parser.config import get_max_retries, get_retry_on_validation_error, get_temp_dir, get_two_pass, resolve


def main() -> None:
    # Backward compat: cv_parser file.pdf -> cv_parser parse file.pdf; cv_parser -i -> cv_parser parse -i
    argv = sys.argv[1:]
    if "parse" not in argv and "export" not in argv and "extract" not in argv:
        if argv and not argv[0].startswith("-"):
            p = Path(argv[0]).expanduser()
            if p.exists() or p.suffix.lower() in (".pdf", ".docx", ".doc"):
                sys.argv = [sys.argv[0], "parse"] + argv
        elif "-i" in argv or "--interactive" in argv:
            sys.argv = [sys.argv[0], "parse"] + argv

    parser = argparse.ArgumentParser(
        description="Parse professor CVs to structured JSON (publications, presentations, recognitions)."
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose logging (API requests, raw responses).",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # parse subcommand
    parse_parser = subparsers.add_parser("parse", help="Parse CV file(s)")
    parse_parser.add_argument(
        "path",
        nargs="*",
        help="Path(s) to PDF or docx. Omit for interactive menu.",
    )
    parse_parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Interactive menu: parse or export.",
    )
    parse_parser.add_argument(
        "--provider",
        "-p",
        choices=["openai", "anthropic", "gemini"],
        default=None,
        help="LLM provider (default: from config or openai)",
    )
    parse_parser.add_argument(
        "--model",
        "-m",
        default=None,
        help="Model name (e.g. gpt-4o). Default from config or provider default.",
    )
    parse_parser.add_argument(
        "--api-key",
        "-k",
        default=None,
        help="API key. Default from config or env.",
    )
    parse_parser.add_argument(
        "--retry",
        action="store_true",
        help="Retry on validation error (default: from config).",
    )
    parse_parser.add_argument(
        "--no-retry",
        action="store_true",
        help="Do not retry on validation error.",
    )
    parse_parser.add_argument(
        "--output",
        "-o",
        help="Write JSON to file instead of stdout.",
    )
    parse_parser.add_argument(
        "--two-pass",
        action="store_true",
        help="Two-pass extraction (default: from config or true).",
    )
    parse_parser.add_argument(
        "--no-two-pass",
        action="store_true",
        help="Single-pass extraction.",
    )
    parse_parser.add_argument(
        "--max-retries",
        type=int,
        default=None,
        metavar="N",
        help="Max retries on validation error (default: from config or 1).",
    )
    parse_parser.add_argument(
        "--output-dir",
        help="Output directory for batch parse (default: output).",
    )
    parse_parser.add_argument(
        "--consolidate",
        help="After batch parse, consolidate to CSV at this path.",
    )
    parse_parser.add_argument(
        "--temp-dir",
        help="Temp dir for topic classification output (default: tmp).",
    )
    parse_parser.add_argument(
        "--use-extracted-text",
        action="store_true",
        help="Feed extracted text to LLM instead of original file (for comparison).",
    )
    parse_parser.add_argument(
        "--text-input",
        metavar="PATH",
        help="Use pre-extracted text: file path (single) or dir with {stem}_raw_lines.txt (batch).",
    )
    parse_parser.add_argument(
        "--model-extraction",
        metavar="MODEL",
        help="Model for extraction pass (default: model).",
    )
    parse_parser.add_argument(
        "--model-classification",
        metavar="MODEL",
        help="Model for classification pass (default: model).",
    )

    # extract subcommand (raw lines only, no LLM)
    extract_parser = subparsers.add_parser("extract", help="Extract raw lines from PDF/DOCX (no LLM)")
    extract_parser.add_argument("path", nargs="+", help="Path(s) to PDF or docx.")
    extract_parser.add_argument(
        "--output-dir",
        "-o",
        default=None,
        help="Output directory (default: tmp). Writes {stem}_raw_lines.txt per file.",
    )

    # export subcommand
    export_parser = subparsers.add_parser("export", help="Consolidate JSON outputs to flat CSV")
    export_parser.add_argument(
        "paths",
        nargs="+",
        help="JSON files from CV parse outputs.",
    )
    export_parser.add_argument(
        "--output",
        "-o",
        help="Output CSV path. Default: stdout.",
    )

    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(name)s: %(message)s")

    if args.command is None:
        args.command = "parse"
        args.path = None
        args.interactive = True
        args.provider = args.model = args.api_key = None
        args.retry = False
        args.no_retry = False
        args.two_pass = False
        args.no_two_pass = False

    prov, mod, key, mod_ext, mod_cls = resolve(
        provider=getattr(args, "provider", None),
        model=getattr(args, "model", None),
        api_key=getattr(args, "api_key", None),
        model_extraction=getattr(args, "model_extraction", None),
        model_classification=getattr(args, "model_classification", None),
    )

    if args.command == "extract":
        out_dir = Path(getattr(args, "output_dir", None) or get_temp_dir()).expanduser().resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        from cv_parser.extract_text import write_raw_lines
        from cv_parser.parser import MIME
        for p in [Path(x).expanduser().resolve() for x in args.path]:
            if not p.exists():
                print(f"Error: file not found: {p}", file=sys.stderr)
                sys.exit(1)
            suffix = p.suffix.lower()
            mime = MIME.get(suffix)
            if not mime:
                print(f"Error: unsupported format {suffix}", file=sys.stderr)
                sys.exit(1)
            out_path = out_dir / f"{p.stem}_raw_lines.txt"
            write_raw_lines(p.read_bytes(), mime, out_path)
            print(f"Wrote {out_path}", file=sys.stderr)
        return

    if args.command == "export":
        paths = [Path(p).expanduser().resolve() for p in args.paths]
        for p in paths:
            if not p.exists():
                print(f"Error: file not found: {p}", file=sys.stderr)
                sys.exit(1)
        out = Path(args.output).expanduser().resolve() if args.output else None
        from cv_parser.combiner import combine_to_flat, load_from_json
        from cv_parser.export import export_csv
        results = load_from_json(paths)
        rows = combine_to_flat(results)
        export_csv(rows, out)
        if out:
            print(f"Wrote {out}", file=sys.stderr)
        return

    # parse command: CLI overrides config
    retry = get_retry_on_validation_error() if not (getattr(args, "retry", False) or getattr(args, "no_retry", False)) else getattr(args, "retry", False)
    two_pass = get_two_pass() if not (getattr(args, "two_pass", False) or getattr(args, "no_two_pass", False)) else getattr(args, "two_pass", True)
    max_retries = getattr(args, "max_retries", None)
    if max_retries is None:
        max_retries = get_max_retries() if retry else 0
    paths_arg = getattr(args, "path", None) or []
    if args.interactive or not paths_arg:
        from cv_parser.cli.interactive import run_menu
        run_menu(
            provider=None,
            model=None,
            api_key=None,
            retry_on_validation_error=retry,
            two_pass=two_pass,
        )
        return

    paths = [Path(p).expanduser().resolve() for p in paths_arg]
    for p in paths:
        if not p.exists():
            print(f"Error: file not found: {p}", file=sys.stderr)
            sys.exit(1)

    temp_dir = Path(getattr(args, "temp_dir", None) or get_temp_dir()).expanduser().resolve()

    if len(paths) > 1:
        out_dir = getattr(args, "output_dir", None) or "output"
        out_dir = Path(out_dir).expanduser().resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            from cv_parser.line_parser import parse_cv_from_lines
            from cv_parser.combiner import combine_to_flat
            from cv_parser.export import export_csv, export_json
            results = [(p, parse_cv_from_lines(p, provider=prov, model=mod, api_key=key)) for p in paths]
            for p, result in results:
                export_json(result, out_dir / f"{p.stem}.json")
            consolidate_path = getattr(args, "consolidate", None)
            if consolidate_path:
                rows = combine_to_flat([r for _, r in results])
                export_csv(rows, Path(consolidate_path).expanduser().resolve())
                print(f"Wrote {consolidate_path}", file=sys.stderr)
            print(f"Wrote {len(results)} JSON file(s) to {out_dir}", file=sys.stderr)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        return

    path = paths[0]
    try:
        from cv_parser.line_parser import parse_cv_from_lines
        from cv_parser.export import export_json
        result = parse_cv_from_lines(path, provider=prov, model=mod, api_key=key)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    out_path = Path(args.output).expanduser().resolve() if args.output else None
    export_json(result, out_path)


if __name__ == "__main__":
    main()
