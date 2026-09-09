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
        # Cria commit ou tag de checkpoint no git
        code, out, _ = run_git_cmd(root, ["status", "--porcelain"])
        if code == 0 and out.strip():
            # Há arquivos modificados antes da tarefa; faz stash ou checkpoint de segurança
            run_git_cmd(root, ["add", "-A"])
            run_git_cmd(root, ["commit", "-m", f"[jinsai-checkpoint] Pre-task {task_id}"])

        # Salva o commit hash atual
        code, commit_hash, _ = run_git_cmd(root, ["rev-parse", "HEAD"])
        if code == 0:
            (checkpoint_dir / "commit.txt").write_text(commit_hash.strip(), encoding="utf-8")
            return {"type": "git", "commit": commit_hash.strip(), "task_id": task_id}

    # Fallback: snapshot simples em diretório .jinsai/checkpoints/
    return {"type": "snapshot", "task_id": task_id, "checkpoint_path": str(checkpoint_dir)}


def get_git_diff(project_root: Path) -> str:
    """Retorna o git diff atual das modificações do projeto."""
    root = project_root.resolve()
    if is_git_repository(root):
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

    if is_git_repository(root) and (checkpoint_dir / "commit.txt").exists():
        commit_hash = (checkpoint_dir / "commit.txt").read_text(encoding="utf-8").strip()
        code, _, err = run_git_cmd(root, ["reset", "--hard", commit_hash])
        # Limpa untracked files criados durante a tarefa
        run_git_cmd(root, ["clean", "-fd"])
        if code == 0:
            logger.info("Rollback via Git para commit '%s' concluído com sucesso.", commit_hash)
            return True
        logger.error("Falha ao executar rollback Git: %s", err)

    return False
