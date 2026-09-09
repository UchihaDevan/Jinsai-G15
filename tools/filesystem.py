"""Ferramentas de Inspeção e Leitura de Arquivos com Guardrails de Segurança.

Permite que os agentes inspecionem a topologia de diretórios, leiam trechos específicos
e compreendam os arquivos de configuração do projeto de forma auditável e controlada.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from tools.security import validate_safe_path

# Extensões e diretórios padrão a ignorar na árvore
IGNORE_TREE_DIRS = {
    ".git",
    "node_modules",
    "venv",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "dist",
    "build",
    ".jinsai",
    ".jinsai_chroma",
}


def list_project_tree(
    project_root: Path,
    max_depth: int = 4,
    max_files: int = 150,
) -> str:
    """Gera uma representação textual da árvore de diretórios do projeto."""
    root = project_root.resolve()
    lines: list[str] = [f"{root.name}/"]
    total_count = 0

    def _walk(current_dir: Path, prefix: str, depth: int) -> None:
        nonlocal total_count
        if depth > max_depth or total_count >= max_files:
            return

        try:
            items = sorted(
                list(current_dir.iterdir()),
                key=lambda p: (not p.is_dir(), p.name.lower()),
            )
        except PermissionError:
            return

        # Filtra itens ignorados
        items = [p for p in items if p.name not in IGNORE_TREE_DIRS and not p.name.startswith(".")]

        for i, item in enumerate(items):
            if total_count >= max_files:
                lines.append(f"{prefix}... (limite de arquivos atingido)")
                return

            is_last = (i == len(items) - 1)
            connector = "└── " if is_last else "├── "
            child_prefix = "    " if is_last else "│   "

            if item.is_dir():
                lines.append(f"{prefix}{connector}{item.name}/")
                total_count += 1
                _walk(item, prefix + child_prefix, depth + 1)
            else:
                lines.append(f"{prefix}{connector}{item.name}")
                total_count += 1

    _walk(root, "", 1)
    return "\n".join(lines)


def read_file(
    project_root: Path,
    relative_path: str,
    start_line: int = 1,
    end_line: int | None = None,
    max_bytes: int = 60000,
) -> str:
    """Lê o conteúdo de um arquivo com intervalo de linhas e limite de bytes."""
    safe_path = validate_safe_path(project_root, relative_path)

    if not safe_path.exists():
        return f"Erro: O arquivo '{relative_path}' não existe."
    if safe_path.is_dir():
        return f"Erro: '{relative_path}' é um diretório, não um arquivo."

    file_size = safe_path.stat().st_size
    if file_size > max_bytes and end_line is None:
        return (
            f"Erro: O arquivo possui {file_size} bytes (excede o limite seguro de {max_bytes} bytes). "
            f"Por favor, especifique 'start_line' e 'end_line' para leitura parcial."
        )

    try:
        with open(safe_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
    except Exception as exc:
        return f"Erro ao ler '{relative_path}': {exc}"

    total_lines = len(all_lines)
    s_idx = max(1, start_line) - 1
    e_idx = min(total_lines, end_line) if end_line else total_lines

    selected = all_lines[s_idx:e_idx]
    formatted = [f"{s_idx + 1 + i:4d} | {line}" for i, line in enumerate(selected)]

    header = f"=== Arquivo: {relative_path} (Linhas {s_idx + 1} a {e_idx} de {total_lines}) ===\n"
    return header + "".join(formatted)


def get_file_metadata(project_root: Path, relative_path: str) -> dict[str, Any]:
    """Retorna metadados detalhados do arquivo: tamanho, linhas, hash SHA-256 e modificação."""
    safe_path = validate_safe_path(project_root, relative_path)

    if not safe_path.exists() or not safe_path.is_file():
        return {"exists": False, "file_path": relative_path}

    hasher = hashlib.sha256()
    line_count = 0
    with open(safe_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
            line_count += chunk.count(b"\n")

    stat = safe_path.stat()
    return {
        "exists": True,
        "file_path": relative_path,
        "size_bytes": stat.st_size,
        "line_count": line_count,
        "sha256": hasher.hexdigest(),
        "mtime": stat.st_mtime,
        "extension": safe_path.suffix,
    }


def read_project_config(project_root: Path) -> dict[str, str]:
    """Lê e resume arquivos chave de configuração do projeto se existirem."""
    root = project_root.resolve()
    config_files = [
        "pyproject.toml",
        "requirements.txt",
        "package.json",
        "Dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        "setup.py",
        "setup.cfg",
        "Makefile",
    ]

    found: dict[str, str] = {}
    for cfg in config_files:
        p = root / cfg
        if p.exists() and p.is_file() and p.stat().st_size < 30000:
            try:
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    found[cfg] = f.read()
            except Exception:
                pass
    return found
