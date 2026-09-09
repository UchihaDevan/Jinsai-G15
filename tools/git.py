"""Gerenciamento de Checkpoints, Diffs e Rollback com Git ou Snapshots Locais.

Permite que o agente reverta alterações caso os testes falhem e colete diffs precisos.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger("jinsai.git")


def is_git_repository(project_root: Path) -> bool:
    """Verifica se o diretório do projeto é um repositório Git."""
    return (project_root / ".git").is_dir() and bool(shutil.which("git"))


def run_git_cmd(project_root: Path, args: list[str]) -> tuple[int, str, str]:
    """Executa comando git dentro do projeto."""
    cmd = ["git", "-C", str(project_root)] + args
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15.0)
        return proc.returncode, proc.stdout, proc.stderr
    except Exception as exc:
        return 1, "", str(exc)


def create_checkpoint(project_root: Path, task_id: str) -> dict[str, Any]:
    """Cria um checkpoint antes de modificar arquivos na tarefa."""
    root = project_root.resolve()
    checkpoint_dir = root / ".jinsai" / "checkpoints" / task_id
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    if is_git_repository(root):
        # Verifica se há alterações não commitadas
        code, out, _ = run_git_cmd(root, ["status", "--porcelain"])
        if code == 0 and out.strip():
            raise RuntimeError(
                "A working tree do Git não está limpa. "
                "O Jinsai exige um repositório sem alterações pendentes "
                "para garantir a segurança dos seus dados."
            )

        # Salva a branch atual para o rollback
        code, current_branch, _ = run_git_cmd(root, ["branch", "--show-current"])
        original_branch = current_branch.strip() or "main"
        (checkpoint_dir / "original_branch.txt").write_text(original_branch, encoding="utf-8")

        # Cria uma branch temporária para isolar a tarefa
        branch_name = f"jinsai-task-{task_id}"
        run_git_cmd(root, ["checkout", "-b", branch_name])

        return {"type": "git", "branch": branch_name, "task_id": task_id}

    # Fallback: snapshot simples em diretório .jinsai/checkpoints/
    return {"type": "snapshot", "task_id": task_id, "checkpoint_path": str(checkpoint_dir)}


def get_git_diff(project_root: Path) -> str:
    """Retorna o git diff atual das modificações do projeto."""
    root = project_root.resolve()
    if is_git_repository(root):
        # Intent to add para garantir que novos arquivos apareçam no diff
        run_git_cmd(root, ["add", "-N", "."])
        
        code, out, _ = run_git_cmd(root, ["diff"])
        if code == 0 and out:
            return out
        # Verifica staged
        code, out, _ = run_git_cmd(root, ["diff", "--cached"])
        if code == 0 and out:
            return out
    return "Nenhuma alteração Git rastreada."


def get_git_status(project_root: Path) -> dict[str, list[str]]:
    """Retorna lista de arquivos modificados, novos e deletados."""
    root = project_root.resolve()
    modified: list[str] = []
    untracked: list[str] = []
    deleted: list[str] = []

    if is_git_repository(root):
        code, out, _ = run_git_cmd(root, ["status", "--porcelain"])
        if code == 0:
            for line in out.splitlines():
                if len(line) < 4:
                    continue
                status = line[:2]
                fname = line[3:].strip()
                if "?" in status:
                    untracked.append(fname)
                elif "D" in status:
                    deleted.append(fname)
                else:
                    modified.append(fname)

    return {"modified": modified, "untracked": untracked, "deleted": deleted}


def rollback_checkpoint(project_root: Path, task_id: str) -> bool:
    """Restaura o estado do projeto para o ponto anterior à tarefa."""
    root = project_root.resolve()
    checkpoint_dir = root / ".jinsai" / "checkpoints" / task_id

    if is_git_repository(root) and (checkpoint_dir / "original_branch.txt").exists():
        original_branch = (checkpoint_dir / "original_branch.txt").read_text(encoding="utf-8").strip()
        
        # O agente pode ter deixado arquivos pendentes, então resetamos as modificações da branch da tarefa
        run_git_cmd(root, ["reset", "--hard", "HEAD"])
        
        # Retorna para a branch original
        code, _, err = run_git_cmd(root, ["checkout", original_branch])
        if code == 0:
            # Tenta apagar a branch da tarefa
            run_git_cmd(root, ["branch", "-D", f"jinsai-task-{task_id}"])
            logger.info("Rollback Git concluído: retornou para branch '%s'.", original_branch)
            return True
        logger.error("Falha ao executar rollback Git: %s", err)

    return False
