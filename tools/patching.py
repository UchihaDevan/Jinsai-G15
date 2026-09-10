"""Ferramentas de Mutação de Arquivos e Aplicação de Patches.

Permite modificações cirúrgicas em arquivos do projeto com garantias de validação prévia,
prevenindo reescritas desnecessárias de arquivos inteiros e respeitando os limites da sandbox.
"""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from tools.security import validate_safe_path


def create_file(
    project_root: Path,
    relative_path: str,
    content: str,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Cria um novo arquivo de código dentro da raiz do projeto."""
    safe_path = validate_safe_path(project_root, relative_path)

    if safe_path.exists() and not overwrite:
        return {
            "success": False,
            "error": f"O arquivo '{relative_path}' já existe. Especifique overwrite=True para sobrescrever.",
        }

    try:
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        with open(safe_path, "w", encoding="utf-8") as f:
            f.write(content)
        return {
            "success": True,
            "file_path": relative_path,
            "bytes_written": len(content.encode("utf-8")),
            "action": "created" if not safe_path.exists() else "overwritten",
        }
    except Exception as exc:
        return {"success": False, "error": f"Falha ao criar arquivo: {exc}"}


def replace_range(
    project_root: Path,
    relative_path: str,
    start_line: int,
    end_line: int,
    new_content: str,
) -> dict[str, Any]:
    """Substitui cirurgicamente um intervalo de linhas em um arquivo existente."""
    safe_path = validate_safe_path(project_root, relative_path)

    if not safe_path.exists():
        return {"success": False, "error": f"Arquivo '{relative_path}' não existe."}

    try:
        with open(safe_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        total = len(lines)
        if start_line < 1 or end_line < start_line or start_line > total + 1:
            return {
                "success": False,
                "error": f"Intervalo inválido ({start_line}-{end_line}). Arquivo possui {total} linhas.",
            }

        # Converte new_content para lista de linhas
        replacement_lines = new_content.splitlines(keepends=True)
        if replacement_lines and not replacement_lines[-1].endswith("\n"):
            replacement_lines[-1] += "\n"

        # Linhas antes, substituição e linhas depois
        prefix = lines[: start_line - 1]
        suffix = lines[end_line:]

        modified_lines = prefix + replacement_lines + suffix

        with open(safe_path, "w", encoding="utf-8") as f:
            f.writelines(modified_lines)

        return {
            "success": True,
            "file_path": relative_path,
            "lines_replaced": end_line - start_line + 1,
            "new_total_lines": len(modified_lines),
        }
    except Exception as exc:
        return {"success": False, "error": f"Falha ao substituir linhas: {exc}"}


def apply_patch(
    project_root: Path,
    relative_path: str,
    target_content: str,
    replacement_content: str,
) -> dict[str, Any]:
    """Aplica uma substituição precisa baseada em conteúdo alvo exato."""
    safe_path = validate_safe_path(project_root, relative_path)

    if not safe_path.exists():
        return {"success": False, "error": f"Arquivo '{relative_path}' não existe."}

    try:
        with open(safe_path, "r", encoding="utf-8") as f:
            full_text = f.read()

        if target_content not in full_text:
            return {
                "success": False,
                "error": "O trecho alvo (target_content) não foi encontrado exatamente como especificado.",
            }

        occurrences = full_text.count(target_content)
        if occurrences > 1:
            return {
                "success": False,
                "error": f"O trecho alvo aparece {occurrences} vezes no arquivo. Especifique mais contexto.",
            }

        new_text = full_text.replace(target_content, replacement_content, 1)
        
        # Atomicidade real via arquivo temporário
        import os
        temp_path = safe_path.with_name(safe_path.name + ".jinsai.tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(new_text)
            os.replace(temp_path, safe_path)
        except Exception as e:
            if temp_path.exists():
                os.remove(temp_path)
            raise e

        return {
            "success": True,
            "file_path": relative_path,
            "action": "patched",
        }
    except Exception as exc:
        return {"success": False, "error": f"Falha ao aplicar patch: {exc}"}


def delete_file(project_root: Path, relative_path: str) -> dict[str, Any]:
    """Remove um arquivo de forma controlada dentro do projeto."""
    safe_path = validate_safe_path(project_root, relative_path)

    if not safe_path.exists():
        return {"success": False, "error": f"Arquivo '{relative_path}' não existe."}

    try:
        safe_path.unlink()
        return {"success": True, "file_path": relative_path, "action": "deleted"}
    except Exception as exc:
        return {"success": False, "error": f"Falha ao remover arquivo: {exc}"}
