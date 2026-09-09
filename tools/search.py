"""Mecanismo de Busca Textual e de Símbolos no Código do Projeto.

Permite que o agente localize ocorrências exatas de classes, funções, imports e strings.
Utiliza ripgrep se disponível no sistema ou mecanismo nativo em Python como fallback.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from tools.security import is_path_blocked, validate_safe_path

SUPPORTED_CODE_EXTS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".json", ".yaml", ".yml",
    ".md", ".html", ".css", ".sh", ".sql", ".c", ".cpp", ".h", ".toml"
}


def search_code(
    project_root: Path,
    query: str,
    is_regex: bool = False,
    max_results: int = 40,
) -> list[dict[str, Any]]:
    """Busca termos no código do projeto e retorna matches estruturados."""
    root = project_root.resolve()
    results: list[dict[str, Any]] = []

    # Tenta usar ripgrep (rg) se instalado
    if shutil.which("rg"):
        try:
            cmd = [
                "rg",
                "-n",
                "--max-count", str(max_results),
                "--glob", "!node_modules",
                "--glob", "!.venv",
                "--glob", "!venv",
                "--glob", "!.git",
            ]
            if not is_regex:
                cmd.append("-F")
            cmd.extend([query, str(root)])

            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10.0)
            for line in proc.stdout.splitlines():
                if len(results) >= max_results:
                    break
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    fpath, lineno, text = parts[0], parts[1], parts[2]
                    try:
                        rel = str(Path(fpath).relative_to(root))
                        if not is_path_blocked(rel):
                            results.append({
                                "file_path": rel,
                                "line_number": int(lineno),
                                "line_content": text.strip(),
                            })
                    except ValueError:
                        continue
            if results:
                return results
        except Exception:
            pass  # Fallback para busca em Python

    # Fallback em Python nativo
    pattern = re.compile(query if is_regex else re.escape(query), re.IGNORECASE)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in {"node_modules", "venv"}]

        for fname in filenames:
            ext = Path(fname).suffix.lower()
            if ext in SUPPORTED_CODE_EXTS:
                full_path = Path(dirpath) / fname
                rel_str = str(full_path.relative_to(root))
                if is_path_blocked(rel_str):
                    continue

                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        for idx, line in enumerate(f, start=1):
                            if pattern.search(line):
                                results.append({
                                    "file_path": rel_str,
                                    "line_number": idx,
                                    "line_content": line.strip(),
                                })
                                if len(results) >= max_results:
                                    return results
                except Exception:
                    continue

    return results
