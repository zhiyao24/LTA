"""Repository-wide safety invariants that should never regress silently."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

from backend.app.constants.commands import CommandType


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = PROJECT_ROOT / "jetson-agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from command_validator import ALLOWED_COMMAND_TYPES  # noqa: E402


def _runtime_python_files() -> list[Path]:
    files = list((PROJECT_ROOT / "backend" / "app").rglob("*.py"))
    files.extend(
        path
        for path in AGENT_ROOT.rglob("*.py")
        if "tests" not in path.relative_to(AGENT_ROOT).parts
    )
    return files


def test_runtime_contains_no_dynamic_or_shell_execution() -> None:
    violations: list[str] = []
    for path in _runtime_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                modules = (
                    [alias.name for alias in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""]
                )
                if any(module == "subprocess" for module in modules):
                    violations.append(f"{path}: imports subprocess")
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
                    violations.append(f"{path}:{node.lineno}: calls {node.func.id}")
                if (
                    isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "os"
                    and node.func.attr == "system"
                ):
                    violations.append(f"{path}:{node.lineno}: calls os.system")

    assert violations == []


def test_backend_and_agent_command_allowlists_match_exactly() -> None:
    backend_allowlist = {command.value for command in CommandType}

    assert backend_allowlist == set(ALLOWED_COMMAND_TYPES)
    assert backend_allowlist == {"STOP", "SET_MODE", "SET_SPEED", "SEND_MESSAGE"}


def test_gitignore_excludes_local_secrets_databases_and_build_outputs() -> None:
    ignore_text = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")

    for required_pattern in ("**/.env", "*.db", ".venv/", "**/node_modules/", "**/dist/"):
        assert required_pattern in ignore_text


def test_frontend_cannot_receive_device_or_provider_credentials() -> None:
    frontend_files = list((PROJECT_ROOT / "frontend" / "src").rglob("*.ts"))
    frontend_files.extend((PROJECT_ROOT / "frontend" / "src").rglob("*.tsx"))
    frontend_files.append(PROJECT_ROOT / "frontend" / ".env.example")
    frontend_text = "\n".join(
        path.read_text(encoding="utf-8") for path in frontend_files
    )

    for forbidden_name in (
        "DEVICE_TOKEN",
        "EXTERNAL_API_KEY",
        "JETSON_API_TOKEN",
        "X-Jetson-Token",
    ):
        assert forbidden_name not in frontend_text


def test_safety_documentation_keeps_physical_controls_outside_software() -> None:
    safety_text = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in (
            PROJECT_ROOT / "README.md",
            PROJECT_ROOT / "AGENTS.md",
            PROJECT_ROOT / "docs" / "hardware-safety.md",
        )
    )

    assert "not a replacement for a physical" in safety_text
    assert "never be the real-time motor-control loop" in safety_text
