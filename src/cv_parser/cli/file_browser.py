"""Interactive file browser for selecting files."""

from pathlib import Path


def browse_and_select(
    start_dir: Path,
    *,
    extensions: tuple[str, ...],
    title: str = "Select files",
) -> list[Path]:
    """Interactive browser: Space or Enter to toggle files, navigate dirs, or Done/Cancel."""
    extensions = tuple(e.lower() for e in extensions)
    start_dir = start_dir.expanduser().resolve()
    if not start_dir.is_dir():
        start_dir = start_dir.parent
    selected: list[Path] = []
    cwd = start_dir

    # Try fzf first (Tab=select, Enter=confirm, Esc=cancel)
    try:
        from pyfzf.pyfzf import FzfPrompt
        fzf = FzfPrompt()
        files = [str(p) for p in cwd.rglob("*") if p.is_file() and p.suffix.lower() in extensions]
        if files:
            result = fzf.prompt(files, "--multi --cycle")
            if result:
                return [Path(p.strip()) for p in result if p.strip()]
            return []
    except (ImportError, FileNotFoundError, Exception):
        pass

    try:
        from questionary.prompts.common import Choice, InquirerControl, Separator, create_inquirer_layout
        from questionary.prompts.checkbox import merge_styles_default
        from prompt_toolkit.application import Application
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.keys import Keys
        from questionary.constants import DEFAULT_QUESTION_PREFIX, DEFAULT_SELECTED_POINTER
        has_pt = True
    except ImportError:
        has_pt = False
        Choice = Separator = None

    def _choices() -> list:
        ch = []
        if has_pt and Choice:
            if cwd.parent != cwd:
                ch.append(Choice("../ (up)", value=".."))
            for p in sorted(cwd.iterdir()):
                if p.is_dir():
                    ch.append(Choice(f"{p.name}/", value=p))
            ch.append(Separator())
            files = [p for p in sorted(cwd.iterdir()) if p.is_file() and p.suffix.lower() in extensions]
            for p in files:
                ch.append(Choice(p.name, value=p, checked=(p in selected)))
            if files:
                ch.append(Choice("Select all", value="select_all"))
            ch.append(Separator("── Done / Cancel ──"))
            ch.append(Choice("Done", value="done"))
            ch.append(Choice("Cancel", value="cancel"))
        else:
            items = []
            if cwd.parent != cwd:
                items.append(("../ (up)", ".."))
            for p in sorted(cwd.iterdir()):
                if p.is_dir():
                    items.append((f"{p.name}/", p))
            files = [p for p in sorted(cwd.iterdir()) if p.is_file() and p.suffix.lower() in extensions]
            for p in files:
                items.append((p.name, p))
            if files:
                items.append(("Select all", "select_all"))
            items.append(("Done", "done"))
            items.append(("Cancel", "cancel"))
            ch = items
        return ch

    def _run_custom_checkbox() -> tuple[str, list]:
        """Run checkbox where Space and Enter both activate (toggle/navigate/trigger)."""
        ch = _choices()
        ic = InquirerControl(ch, pointer=DEFAULT_SELECTED_POINTER, use_indicator=True)

        def get_tokens():
            tokens = [
                ("class:qmark", f"{DEFAULT_QUESTION_PREFIX} "),
                ("class:question", f" {title} — {cwd} "),
                ("class:instruction", f"  Selected: {len(ic.selected_options)} file(s)  "),
                ("class:instruction", "(↑↓ move  Space/Enter: select, Select all, open dir, Done/Cancel)\n"),
            ]
            return tokens

        layout = create_inquirer_layout(ic, get_tokens)

        def activate(event):
            choice = ic.get_pointed_at()
            if isinstance(choice, Separator) or choice.disabled:
                return
            val = choice.value
            if val == "cancel":
                ic.is_answered = True
                event.app.exit(result=("cancel", []))
            elif val == "done":
                ic.is_answered = True
                event.app.exit(result=("done", [c.value for c in ic.choices if not isinstance(c, Separator) and c.value in ic.selected_options and isinstance(c.value, Path) and c.value.is_file()]))
            elif val == ".." or (isinstance(val, Path) and val.is_dir()):
                ic.is_answered = True
                event.app.exit(result=("navigate", val))
            elif val == "select_all":
                files = [c.value for c in ic.choices if isinstance(c.value, Path) and c.value.is_file()]
                all_selected = all(f in ic.selected_options for f in files)
                for f in files:
                    if all_selected and f in ic.selected_options:
                        ic.selected_options.remove(f)
                    elif not all_selected and f not in ic.selected_options:
                        ic.selected_options.append(f)
            else:
                if val in ic.selected_options:
                    ic.selected_options.remove(val)
                else:
                    ic.selected_options.append(val)

        bindings = KeyBindings()

        @bindings.add(Keys.ControlQ, eager=True)
        @bindings.add(Keys.ControlC, eager=True)
        def _(e):
            e.app.exit(exception=KeyboardInterrupt, style="class:aborting")

        @bindings.add(" ", eager=True)
        def on_space(e):
            activate(e)

        @bindings.add(Keys.ControlM, eager=True)
        def on_enter(e):
            activate(e)

        def move_down(e):
            ic.select_next()
            while not ic.is_selection_valid():
                ic.select_next()

        def move_up(e):
            ic.select_previous()
            while not ic.is_selection_valid():
                ic.select_previous()

        bindings.add(Keys.Down, eager=True)(move_down)
        bindings.add(Keys.Up, eager=True)(move_up)
        bindings.add("j", eager=True)(move_down)
        bindings.add("k", eager=True)(move_up)

        @bindings.add(Keys.Any)
        def noop(_):
            pass

        app = Application(layout=layout, key_bindings=bindings, style=merge_styles_default([]))
        result = app.run()
        if isinstance(result, BaseException):
            raise result
        return result

    while True:
        if not has_pt:
            print(f"\n{title} — {cwd}")
            print("  Selected:", len(selected), "file(s)")
            items = _choices()
            for i, c in enumerate(items, 1):
                lbl = c[0] if isinstance(c, tuple) else getattr(c, "title", c)
                print(f"  {i}. {lbl}")
            idx = input("Choice (0=cancel): ").strip()
            if idx == "0":
                return []
            try:
                pick = items[int(idx) - 1][1] if isinstance(items[0], tuple) else items[int(idx) - 1].value
            except (ValueError, IndexError):
                break
        else:
            try:
                action, payload = _run_custom_checkbox()
            except KeyboardInterrupt:
                return []
            if action == "cancel":
                return []
            if action == "done":
                selected = [p for p in selected if p.parent != cwd]
                for r in payload:
                    if isinstance(r, Path) and r.is_file():
                        selected.append(r)
                return list(dict.fromkeys(selected))
            if action == "navigate":
                if payload == "..":
                    cwd = cwd.parent
                else:
                    cwd = payload
                continue

        # Fallback
        if pick == "cancel":
            return []
        if pick == "done":
            break
        if pick == "..":
            cwd = cwd.parent
            continue
        if pick == "select_all":
            files = [p for p in cwd.iterdir() if p.is_file() and p.suffix.lower() in extensions]
            selected = [p for p in selected if p.parent != cwd]
            all_selected = all(f in selected for f in files)
            for f in files:
                if all_selected and f in selected:
                    selected.remove(f)
                elif not all_selected and f not in selected:
                    selected.append(f)
            selected = list(dict.fromkeys(selected))
            continue
        if isinstance(pick, Path) and pick.is_dir():
            cwd = pick
            continue
        if isinstance(pick, Path) and pick.is_file():
            selected = [p for p in selected if p.parent != cwd]
            if pick not in selected:
                selected.append(pick)
            selected = list(dict.fromkeys(selected))

    return selected
