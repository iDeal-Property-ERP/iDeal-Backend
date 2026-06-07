import ast
import os
from pathlib import Path

import pytest

SOURCE_ROOT = Path(__file__).resolve().parent.parent.parent.parent

EXCLUDE_DIRS = {
    "tests",
    "migrations",
    "__pycache__",
    "management",
}

TRANSLATION_FUNC_NAMES = {"_", "gettext", "gettext_lazy", "gettext_noop"}


def _is_gettext_call(node):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return node.func.id in TRANSLATION_FUNC_NAMES
    return False


def _body_of_class(tree, class_node):
    return list(ast.iter_child_nodes(class_node))


def _scan_file(filepath):
    try:
        tree = ast.parse(filepath.read_text(), filename=str(filepath))
    except SyntaxError:
        return []

    violations = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue

            if (
                target.id in ("verbose_name", "verbose_name_plural", "help_text")
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
                and not _is_gettext_call(node.value)
            ):
                violations.append((node.lineno, target.id, node.value.value))

            if target.id == "CHOICES" and isinstance(node.value, ast.List):
                for elt in node.value.elts:
                    if isinstance(elt, ast.Tuple) and len(elt.elts) == 2:
                        display = elt.elts[1]
                        if (
                            isinstance(display, ast.Constant)
                            and isinstance(display.value, str)
                            and not _is_gettext_call(display)
                        ):
                            violations.append((display.lineno, "CHOICES", display.value))

    return violations


def _should_exclude(filepath):
    if filepath.suffix != ".py":
        return True
    parts = set(filepath.relative_to(SOURCE_ROOT).parts)
    return bool(parts & EXCLUDE_DIRS)


def collect_untranslated():
    violations = []

    for root, dirs, files in os.walk(SOURCE_ROOT):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith("__pycache__")]
        for filename in files:
            filepath = Path(root) / filename
            if _should_exclude(filepath):
                continue
            for line, context, text in _scan_file(filepath):
                rel = filepath.relative_to(SOURCE_ROOT)
                violations.append((rel, line, context, text))

    return violations


@pytest.mark.unit
def test_no_untranslated_user_facing_strings():
    violations = collect_untranslated()
    if violations:
        msg = "Untranslated user-facing strings found:\n"
        for relpath, line, context, text in violations:
            msg += f'  {relpath}:{line}  [{context}]  "{text}"\n'
        pytest.fail(msg)
