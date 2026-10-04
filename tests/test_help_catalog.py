"""K3: /help catalog contract — the inventory must match the real handlers.

The ast guard supports the registration style `from aiogram.filters import
Command` and collects every positional string-literal command name, so
`Command("a", "b")` contributes both `a` and `b`; a positional argument that is
not a string literal fails loudly. Deliberately unsupported (residual, no
current handler uses them): the `commands=[...]` keyword form and the
`aiogram.filters.command.*` import path.
"""

import ast
from pathlib import Path

import pytest

import texts
from services.help import (
    AUDIENCE_ABSENCE,
    AUDIENCE_ADMIN,
    AUDIENCE_ALL,
    AUDIENCE_MANAGER,
    HELP_COMMANDS,
    open_commands,
)

ROOT = Path(__file__).resolve().parents[1]

# Canonical aiogram filters that register a slash command. Only `Command` names
# a command; `CommandStart` is recognized so it can be ignored, not crash.
_COMMAND_FILTERS = {"Command", "CommandStart"}


def _bound_filter_names(tree: ast.Module) -> dict[str, str]:
    """Local names imported from aiogram.filters, mapped to the original filter.

    `from aiogram.filters import Command as Cmd` maps ``"Cmd" -> "Command"``.
    """
    names: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "aiogram.filters":
            for alias in node.names:
                if alias.name in _COMMAND_FILTERS:
                    names[alias.asname or alias.name] = alias.name
    return names


def _module_bindings(tree: ast.Module) -> dict[str, str]:
    """Local names bound to modules, mapped to fully-qualified module paths.

    Covers every way ``aiogram.filters`` can be referenced::

        import aiogram                    -> {"aiogram": "aiogram"}
        import aiogram.filters            -> {"aiogram": "aiogram"}
        import aiogram.filters as af      -> {"af": "aiogram.filters"}
        from aiogram import filters       -> {"filters": "aiogram.filters"}
        from aiogram import filters as f  -> {"f": "aiogram.filters"}
    """
    bindings: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    bindings[alias.asname] = alias.name
                else:
                    top_level = alias.name.split(".")[0]
                    bindings[top_level] = top_level
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                bindings[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return bindings


def _resolve_qname(node: ast.expr, bindings: dict[str, str]) -> str | None:
    """Fully-qualified module path an expression resolves to, else None.

    ``ast.Name`` looks up the local binding; ``ast.Attribute`` appends the
    attribute to the resolved base (``af`` -> ``aiogram.filters`` becomes
    ``aiogram.filters.Command``). Anything else is unresolvable.
    """
    if isinstance(node, ast.Name):
        return bindings.get(node.id)
    if isinstance(node, ast.Attribute):
        base = _resolve_qname(node.value, bindings)
        if base is None:
            return None
        return f"{base}.{node.attr}"
    return None


def _command_filter_name(
    call: ast.Call, bound_names: dict[str, str], bindings: dict[str, str]
) -> str | None:
    """The canonical filter name (``Command``/``CommandStart``) of a call, else None.

    Only calls resolving to aiogram.filters count: imported local names and
    attribute calls whose base resolves to the module (``aiogram.filters.Command``,
    ``af.Command``, ``filters.Command``). An unrelated ``Foo.Command(...)`` is
    rejected.
    """
    func = call.func
    if isinstance(func, ast.Name):
        return bound_names.get(func.id)
    if isinstance(func, ast.Attribute) and func.attr in _COMMAND_FILTERS:
        if _resolve_qname(func.value, bindings) == "aiogram.filters":
            return func.attr
    return None


def _string_literals(call: ast.Call, source: str) -> list[str]:
    """All positional string-literal arguments of a call, in order.

    Fails loudly (with `file:lineno`) on a positional argument that is not a
    string literal, so a computed command name cannot slip past the guard.
    """
    names: list[str] = []
    for arg in call.args:
        if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
            raise AssertionError(
                f"{source}:{arg.lineno}: command filter needs string literals "
                "as positional arguments"
            )
        names.append(arg.value)
    return names


def _commands_from_tree(tree: ast.Module, source: str) -> set[str]:
    """Named slash-command strings in one parsed module.

    Only `Command` carries names; `CommandStart` never names a command, so it is
    recognized and ignored (a no-arg `CommandStart()` must not crash the guard).
    Every positional string-literal argument of a `Command` call is collected; a
    call with no literals, or with a computed positional argument, fails loudly.
    """
    commands: set[str] = set()
    bound_names = _bound_filter_names(tree)
    bindings = _module_bindings(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        filter_name = _command_filter_name(node, bound_names, bindings)
        if filter_name is None or filter_name == "CommandStart":
            continue
        command_names = _string_literals(node, source)
        if not command_names:
            raise AssertionError(
                f"{source}:{node.lineno}: command filter needs a string literal "
                "as its first argument"
            )
        commands.update(command_names)
    return commands


def _handler_commands() -> set[str]:
    """Command names registered in handlers/*.py, collected via `ast`."""
    commands: set[str] = set()
    for path in (ROOT / "handlers").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        commands |= _commands_from_tree(tree, path.name)
    return commands


def test_catalog_matches_handlers():
    assert {entry.command for entry in HELP_COMMANDS} == _handler_commands()


def test_help_entries_are_documented():
    known_audiences = {AUDIENCE_ALL, AUDIENCE_ABSENCE, AUDIENCE_MANAGER, AUDIENCE_ADMIN}
    for entry in HELP_COMMANDS:
        assert entry.description
        assert entry.audience in known_audiences


def test_catalog_order_is_locked():
    assert [entry.command for entry in HELP_COMMANDS] == [
        "start",
        "help",
        "cancel",
        "pending",
        "promote",
        "demote",
        "remove",
        "sethead",
    ]


def test_open_commands_are_start_and_help():
    commands = open_commands()
    assert [entry.command for entry in commands] == ["start", "help"]
    assert commands[0].description == texts.HELP_CMD_START
    assert commands[1].description == texts.HELP_CMD_HELP


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('import aiogram.filters\naiogram.filters.Command("bar")', {"bar"}),
        ('import aiogram.filters as af\naf.Command("baz")', {"baz"}),
        ('import aiogram\naiogram.filters.Command("qux")', {"qux"}),
        ('from aiogram import filters\nfilters.Command("x")', {"x"}),
        ('from aiogram import filters as f\nf.Command("y")', {"y"}),
        ('from aiogram.filters import Command as Cmd\nCmd("foo")', {"foo"}),
        ('from aiogram.filters import Command\nCommand("a", "b")', {"a", "b"}),
    ],
)
def test_aiogram_filters_reference_is_collected(source, expected):
    tree = ast.parse(source)
    assert _commands_from_tree(tree, "snippet") == expected


@pytest.mark.parametrize(
    "source",
    [
        'Foo.Command("nope")',
        'Foo.Bar.Command("nope")',
        'aiogram = object()\naiogram.filters.Command("evil")',
    ],
)
def test_non_aiogram_attribute_call_is_not_collected(source):
    tree = ast.parse(source)
    assert _commands_from_tree(tree, "snippet") == set()


@pytest.mark.parametrize("source", ["CommandStart()", 'CommandStart("x")'])
def test_command_start_contributes_nothing(source):
    tree = ast.parse(f"from aiogram.filters import CommandStart\n{source}")
    assert _commands_from_tree(tree, "snippet") == set()


@pytest.mark.parametrize("source", ['Command(f"x")', "Command(name)", "Command()"])
def test_command_without_literal_fails(source):
    tree = ast.parse(f"from aiogram.filters import Command\n{source}")
    with pytest.raises(AssertionError):
        _commands_from_tree(tree, "snippet")
