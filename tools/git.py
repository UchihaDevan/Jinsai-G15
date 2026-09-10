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

    if is_git_repository(root):
        # Verifica se há alterações não commitadas ANTES de criar diretórios
        code, out, _ = run_git_cmd(root, ["status", "--porcelain"])
        
        # Filtra o diretório .jinsai para evitar falso-positivo se o usuário não o ignorou
        out_filtered = [line for line in out.splitlines() if not line[3:].startswith(".jinsai/")]
        if code == 0 and out_filtered:
            raise RuntimeError(
                "A working tree do Git não está limpa. "
                "O Jinsai exige um repositório sem alterações pendentes "
                "para garantir a segurança dos seus dados."
            )

        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        # Salva a branch atual para o rollback
        code, current_branch, _ = run_git_cmd(root, ["branch", "--show-current"])
        original_branch = current_branch.strip() or "main"
        (checkpoint_dir / "original_branch.txt").write_text(original_branch, encoding="utf-8")
        
        # Salva o commit base atual
        code, base_commit, _ = run_git_cmd(root, ["rev-parse", "HEAD"])
        if code == 0:
            (checkpoint_dir / "base_commit.txt").write_text(base_commit.strip(), encoding="utf-8")

        # Salva timestamp de criação
        from datetime import datetime, timezone
        (checkpoint_dir / "created_at.txt").write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")

        # Cria uma branch temporária para isolar a tarefa
        branch_name = f"jinsai-task-{task_id}"
        code, _, err = run_git_cmd(root, ["checkout", "-b", branch_name])
        if code != 0:
            raise RuntimeError(f"Falha ao criar branch da tarefa '{branch_name}': {err}")
            
        (checkpoint_dir / "task_branch.txt").write_text(branch_name, encoding="utf-8")

        return {"type": "git", "branch": branch_name, "task_id": task_id}

    # Fallback: snapshot simples em diretório .jinsai/checkpoints/
    return {"type": "snapshot", "task_id": task_id, "checkpoint_path": str(checkpoint_dir)}


def get_git_diff(project_root: Path) -> str:
    """Retorna o git diff atual, incluindo conteúdo de novos arquivos permitidos."""
    from tools.security import is_path_blocked
    root = project_root.resolve()
    if is_git_repository(root):
        # Diff dos arquivos modificados rastreados
        code, out, _ = run_git_cmd(root, ["diff"])
        code_staged, out_staged, _ = run_git_cmd(root, ["diff", "--cached"])
        diff_text = (out or "") + "\n" + (out_staged or "")
        
        # Lê os arquivos untracked (não rastreados) para anexar ao diff
        code_ut, untracked_files, _ = run_git_cmd(root, ["ls-files", "--others", "--exclude-standard"])
        if code_ut == 0 and untracked_files.strip():
            for f in untracked_files.strip().splitlines():
                if is_path_blocked(f):
                    continue
                filepath = root / f
                if filepath.is_file() and filepath.stat().st_size < 50000:
                    try:
                        content = filepath.read_text(encoding="utf-8")
                        diff_text += f"\n--- /dev/null\n+++ b/{f}\n@@ -0,0 +1,{len(content.splitlines())} @@\n"
                        diff_text += "".join([f"+{line}\n" for line in content.splitlines()])
                    except Exception:
                        pass # ignora arquivos binários ou de erro na leitura

        if diff_text.strip():
            return diff_text.strip()
            
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
    """Restaura o estado do projeto retornando à branch original de forma segura."""
    root = project_root.resolve()
    checkpoint_dir = root / ".jinsai" / "checkpoints" / task_id

    if is_git_repository(root) and (checkpoint_dir / "original_branch.txt").exists():
        original_branch = (checkpoint_dir / "original_branch.txt").read_text(encoding="utf-8").strip()
        expected_task_branch = f"jinsai-task-{task_id}"
        
        # Verifica se ainda estamos na branch correta da tarefa
        code, current_branch, _ = run_git_cmd(root, ["branch", "--show-current"])
        
        if current_branch.strip() == expected_task_branch:
            # Verifica se o HEAD mudou em relação ao commit base
            code, current_commit, _ = run_git_cmd(root, ["rev-parse", "HEAD"])
            base_commit = ""
            if (checkpoint_dir / "base_commit.txt").exists():
                base_commit = (checkpoint_dir / "base_commit.txt").read_text(encoding="utf-8").strip()
            
            if current_commit.strip() == base_commit:
                # O agente não comitou nada novo, apenas deixou arquivos sujos.
                # Limpamos o working tree da branch da tarefa antes do checkout.
                run_git_cmd(root, ["reset", "--hard", "HEAD"])
                logger.info("Rollback executou reset --hard para limpar modificações não commitadas.")
            else:
                logger.warning("Rollback pulou o 'reset --hard': a branch da tarefa possui commits inesperados.")
                # Se não podemos resetar, fazemos checkout da original mas os arquivos modificados
                # da tarefa vão conflitar. Fazemos reset para limpar e permitir o checkout.
                # Mas como a política pede restrição, tentamos checkout normal.
        else:
            logger.warning("Rollback ignorou o 'reset --hard': não estamos na branch da tarefa esperada.")
        
        # Retorna para a branch original
        code, _, err = run_git_cmd(root, ["checkout", original_branch])
        if code == 0:
            logger.info(
                "Rollback Git concluído: retornou para branch '%s'. "
                "A branch da tarefa '%s' foi preservada para inspeção manual.", 
                original_branch, expected_task_branch
            )
            return True
        logger.error("Falha ao executar rollback Git: %s", err)

    return False
