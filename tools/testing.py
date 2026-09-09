"""Execução Segura de Testes Unitários e Validações Sintáticas.

Executa pytest, py_compile e linters de forma isolada com controle de timeout,
retornando stdout e stderr para alimentar o loop de reparação (repair loop) do agente.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from tools.security import is_command_safe, validate_safe_path

logger = logging.getLogger("jinsai.testing")


def run_syntax_check(project_root: Path, relative_path: str) -> dict[str, Any]:
    """Valida a sintaxe de um arquivo Python usando py_compile."""
    safe_path = validate_safe_path(project_root, relative_path)
    if not safe_path.suffix == ".py":
        return {"success": True, "message": "Arquivo não é Python; sintaxe pulada."}

    cmd = [sys.executable, "-m", "py_compile", str(safe_path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5.0)
        return {
            "success": proc.returncode == 0,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "file_path": relative_path,
        }
    except Exception as exc:
        return {"success": False, "stderr": str(exc), "file_path": relative_path}


def run_unit_tests(
    project_root: Path,
    test_target: str | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Executa suíte de testes com pytest de forma segura."""
    root = project_root.resolve()

    # Detectar interpretador python e pytest
    venv_pytest = root / "venv" / "bin" / "pytest"
    local_venv_pytest = root / ".venv" / "bin" / "pytest"

    if venv_pytest.exists():
        pytest_cmd = str(venv_pytest)
    elif local_venv_pytest.exists():
        pytest_cmd = str(local_venv_pytest)
    elif shutil.which("pytest"):
        pytest_cmd = "pytest"
    else:
        # Fallback usando python -m unittest
        pytest_cmd = None

    if pytest_cmd:
        cmd = [pytest_cmd, "-v", "--tb=short"]
        if test_target:
            safe_target = validate_safe_path(root, test_target)
            cmd.append(str(safe_target.relative_to(root)))
    else:
        cmd = [sys.executable, "-m", "unittest", "discover", "-s", "tests"]

    try:
        logger.info("Executando testes: %s", " ".join(cmd))
        proc = subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        passed = proc.returncode == 0
        return {
            "passed": passed,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "cmd": " ".join(cmd),
        }
    except subprocess.TimeoutExpired:
        return {
            "passed": False,
            "returncode": -1,
            "stdout": "",
            "stderr": f"Erro: Tempo limite de execução de testes ({timeout}s) excedido.",
            "cmd": " ".join(cmd),
        }
    except Exception as exc:
        return {
            "passed": False,
            "returncode": -1,
            "stdout": "",
            "stderr": f"Falha ao disparar testes: {exc}",
            "cmd": " ".join(cmd),
        }
