"""Format CVParseResult for terminal display."""

from cv_parser.schemas import CVParseResult, Usage


def format_usage(usage: Usage) -> str:
    """Format token usage summary."""
    try:
        from rich.console import Console
        from rich.table import Table
        console = Console(force_terminal=True)
        t = Table(title="Token usage")
        t.add_column("Input", style="cyan")
        t.add_column("Output", style="green")
        t.add_column("Total", style="yellow")
        t.add_row(str(usage.input_tokens), str(usage.output_tokens), str(usage.input_tokens + usage.output_tokens))
        with console.capture() as c:
            console.print(t)
        return c.get()
    except ImportError:
        return f"Tokens: input={usage.input_tokens}, output={usage.output_tokens}, total={usage.input_tokens + usage.output_tokens}\n"


def format_result(result: CVParseResult) -> str:
    """Format CVParseResult for terminal display."""
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console(force_terminal=True)
        m = result.metadata
        if m.name or m.email or m.phone:
            t = Table(title="Professor")
            t.add_column("Name", style="cyan")
            t.add_column("Email", style="green")
            t.add_column("Phone", style="yellow")
            t.add_row(m.name or "-", m.email or "-", m.phone or "-")
            with console.capture() as c:
                console.print(t)
            out = c.get()
        else:
            out = ""
        if result.publications:
            t = Table(title=f"Publications ({len(result.publications)})")
            t.add_column("Year", style="cyan")
            t.add_column("Type", style="green")
            t.add_column("Status", style="yellow")
            t.add_column("Title", style="white")
            t.add_column("Role", style="magenta")
            t.add_column("Institution", style="blue")
            for p in result.publications:
                t.add_row(
                    str(p.year),
                    p.type.value,
                    p.status.value,
                    p.title[:50] + "..." if len(p.title) > 50 else p.title,
                    p.role.value,
                    p.institution[:30] + "..." if len(p.institution) > 30 else p.institution,
                )
            with console.capture() as c:
                console.print(t)
            out += ("\n" if out else "") + c.get()
        else:
            out = out or ""

        if result.presentations:
            t = Table(title=f"Presentations ({len(result.presentations)})")
            t.add_column("Year", style="cyan")
            t.add_column("Type", style="green")
            t.add_column("Title", style="white")
            t.add_column("Role", style="magenta")
            t.add_column("Institution", style="blue")
            for p in result.presentations:
                t.add_row(
                    str(p.year),
                    p.type.value,
                    p.title[:50] + "..." if len(p.title) > 50 else p.title,
                    p.role.value,
                    p.institution[:30] + "..." if len(p.institution) > 30 else p.institution,
                )
            with console.capture() as c:
                console.print(t)
            out += "\n" + c.get()

        if result.recognitions:
            t = Table(title=f"Recognitions ({len(result.recognitions)})")
            t.add_column("Year", style="cyan")
            t.add_column("Title", style="white")
            t.add_column("Institution", style="blue")
            for r in result.recognitions:
                t.add_row(
                    str(r.year),
                    r.title[:50] + "..." if len(r.title) > 50 else r.title,
                    r.institution[:30] + "..." if len(r.institution) > 30 else r.institution,
                )
            with console.capture() as c:
                console.print(t)
            out += "\n" + c.get()

        return out.strip() if out else "No data extracted."
    except ImportError:
        return _format_plain(result)


def _format_plain(result: CVParseResult) -> str:
    """Plain text fallback when rich is not available."""
    lines: list[str] = []
    m = result.metadata
    if m.name or m.email or m.phone:
        if m.name:
            lines.append(f"Name: {m.name}")
        if m.email:
            lines.append(f"Email: {m.email}")
        if m.phone:
            lines.append(f"Phone: {m.phone}")
        lines.append("")
    if result.publications:
        lines.append(f"Publications ({len(result.publications)}):")
        for p in result.publications:
            lines.append(f"  - {p.year} | {p.type.value} | {p.status.value} | {p.title} | {p.role.value} | {p.institution}")
    if result.presentations:
        lines.append(f"Presentations ({len(result.presentations)}):")
        for p in result.presentations:
            lines.append(f"  - {p.year} | {p.type.value} | {p.title} | {p.role.value} | {p.institution}")
    if result.recognitions:
        lines.append(f"Recognitions ({len(result.recognitions)}):")
        for r in result.recognitions:
            lines.append(f"  - {r.year} | {r.title} | {r.institution}")
    return "\n".join(lines) if lines else "No data extracted."
