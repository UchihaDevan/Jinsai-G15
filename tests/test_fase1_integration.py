import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from memory.project_memory import ProjectMemory
from tools.git import create_checkpoint, get_git_diff, rollback_checkpoint
from tools.crew_wrappers import CreateFileTool, ApplyPatchTool


def test_fase1_integration():
    """
    Testa todo o fluxo da Fase 1 em um repositório git temporário.
    """
    # 1. Branch limpa em repo temporário
    temp_dir = tempfile.mkdtemp(prefix="jinsai_test_")
    project_root = Path(temp_dir)
    try:
        subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True)
        (project_root / "README.md").write_text("# Teste Jinsai\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=project_root, check=True)
        # Git config pode ser necessário no ambiente CI, usando dev/null fallback
        subprocess.run(["git", "config", "user.email", "test@jinsai.local"], cwd=project_root)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=project_root)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=project_root, check=True)

        task_id = "task_integration_001"

        # 2. create_checkpoint()
        checkpoint = create_checkpoint(project_root, task_id)
        assert checkpoint["branch"] == f"jinsai-task-{task_id}"

        # 3. inicialização de ProjectMemory
        mem = ProjectMemory(project_root)
        mem.update_task_state(task_id, "PLANNED")
        
        # 4. criação de CreateFileTool e ApplyPatchTool e 5. alteração real
        create_tool = CreateFileTool(project_root=project_root)
        patch_tool = ApplyPatchTool(project_root=project_root)

        # Usando as tools
        create_tool._run("novo.py", "def foo():\n    pass\n")
        patch_tool._run("README.md", "# Teste Jinsai\n", "# Teste Jinsai\n\nAdicionado via patch!\n")

        # Verifica se os arquivos mudaram
        assert (project_root / "novo.py").exists()
        assert "Adicionado via patch!" in (project_root / "README.md").read_text()

        # 6. get_git_diff()
        diff = get_git_diff(project_root)
        assert "novo.py" in diff
        assert "Adicionado via patch" in diff

        # 7. atualização de estados
        mem.update_task_state(task_id, "IN_PROGRESS")
        states = mem.get_task_states()
        assert states[task_id]["status"] == "IN_PROGRESS"

        # 8. rollback
        rollback_checkpoint(project_root, task_id)

        # 9. preservação da branch original
        code = subprocess.run(["git", "branch", "--show-current"], cwd=project_root, capture_output=True, text=True)
        assert code.stdout.strip() in ["main", "master"]

        # E a branch da tarefa deve estar preservada
        code = subprocess.run(["git", "branch"], cwd=project_root, capture_output=True, text=True)
        assert f"jinsai-task-{task_id}" in code.stdout

        print("✔ Teste de integração da Fase 1 passou com sucesso!")

        # Teste extra: Criação de branch duplicada e detecção
        try:
            create_checkpoint(project_root, task_id)
            assert False, "Deveria ter falhado ao tentar criar a mesma branch novamente."
        except RuntimeError as e:
            assert "A working tree do Git não está limpa" in str(e) or "Falha ao criar branch" in str(e)

        print("✔ Teste de branch duplicada/working tree suja passou com sucesso!")

    finally:
        shutil.rmtree(temp_dir)

if __name__ == "__main__":
    test_fase1_integration()
