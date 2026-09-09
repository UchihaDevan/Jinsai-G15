"""Suíte de Testes da Base do Jinsai-G15 v3.0.

Valida:
1. Importação de todos os módulos do núcleo, ferramentas e memória.
2. Carregamento e integridade dos arquivos YAML de configuração.
3. Roteamento de tarefas (determinístico e heurístico).
4. Guardrails de segurança (anti path-traversal e bloqueio de segredos).
5. Ferramentas de mutação de arquivo (create_file, replace_range, apply_patch).
6. Máquina de estados finita e ciclo de reparação.
7. Memória de projeto (.jinsai/decisions.md e task_state.json).
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest
import yaml

# 1. Teste de Importação dos Módulos
def test_imports():
    from core.vram_manager import VRAMManager
    from core.router import TaskRouter
    from core.rag_engine import LocalCodeRAG
    from core.errors import SecurityViolationError, OllamaUnavailableError
    from core.state_machine import DevelopmentStateMachine, DevelopmentState
    from tools.security import validate_safe_path, is_path_blocked, is_command_safe
    from tools.filesystem import list_project_tree, read_file, get_file_metadata
    from tools.patching import create_file, replace_range, apply_patch
    from tools.git import create_checkpoint, get_git_status
    from tools.testing import run_syntax_check, run_unit_tests
    from memory.project_memory import ProjectMemory

    assert VRAMManager is not None
    assert TaskRouter is not None
    assert DevelopmentStateMachine is not None


# 2. Teste de Carregamento dos Arquivos YAML
def test_yaml_configurations():
    config_dir = Path(__file__).parent.parent / "config"
    presets_path = config_dir / "presets.yaml"
    agents_path = config_dir / "agents.yaml"
    tasks_path = config_dir / "tasks.yaml"

    assert presets_path.exists(), "presets.yaml deve existir"
    assert agents_path.exists(), "agents.yaml deve existir"
    assert tasks_path.exists(), "tasks.yaml deve existir"

    with open(presets_path, "r", encoding="utf-8") as f:
        presets = yaml.safe_load(f)
    assert "presets" in presets
    assert "offline" in presets["presets"]
    assert "precision" in presets["presets"]

    with open(agents_path, "r", encoding="utf-8") as f:
        agents = yaml.safe_load(f)
    assert "manager" in agents
    assert "developer" in agents

    with open(tasks_path, "r", encoding="utf-8") as f:
        tasks = yaml.safe_load(f)
    assert "plan_task" in tasks
    assert "implement_task" in tasks


# 3. Teste do Roteador de Tarefas
def test_router_logic():
    from core.router import TaskRouter

    router = TaskRouter()

    # Tarefa arquitetural complexa
    dec_arch = router.route("Refatore toda a arquitetura de autenticação para suportar microserviços")
    assert dec_arch.is_complex is True
    assert dec_arch.requires_cloud_manager is True

    # Tarefa pontual local
    dec_local = router.route("adicione um docstring nesta função")
    assert dec_local.is_complex is False
    assert dec_local.requires_cloud_manager is False

    # Tarefa que menciona arquivo existente com projeto ativo
    dec_rag = router.route("Como a classe User está implementada no arquivo auth.py?", has_project_path=True)
    assert dec_rag.requires_rag is True


# 4. Teste de Segurança e Sandboxing
def test_security_guardrails():
    from tools.security import validate_safe_path, is_path_blocked, is_command_safe
    from core.errors import SecurityViolationError

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Caminho válido dentro da raiz
        valid = validate_safe_path(root, "src/main.py")
        assert valid == root / "src" / "main.py"

        # Tentativa de Path Traversal fora da raiz
        with pytest.raises(SecurityViolationError):
            validate_safe_path(root, "../../etc/passwd")

        # Tentativa de acessar arquivo bloqueado (.env)
        assert is_path_blocked(".env") is True
        assert is_path_blocked(".env.production") is True
        assert is_path_blocked("id_rsa") is True
        assert is_path_blocked("credentials.json") is True
        assert is_path_blocked("src/app.py") is False

        with pytest.raises(SecurityViolationError):
            validate_safe_path(root, ".env")

        # Checagem de comandos perigosos
        safe, reason = is_command_safe("pytest tests/")
        assert safe is True

        unsafe, reason = is_command_safe("rm -rf /")
        assert unsafe is False
        assert "destrutivo" in reason.lower()


# 5. Teste de Ferramentas de Mutação de Arquivo
def test_patching_tools():
    from tools.patching import create_file, replace_range, apply_patch

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # 1. Criação de arquivo
        res_create = create_file(root, "calc.py", "def add(a, b):\n    return a + b\n")
        assert res_create["success"] is True
        file_path = root / "calc.py"
        assert file_path.exists()

        # 2. Substituição cirúrgica por intervalo
        new_fn = "def add(a: int, b: int) -> int:\n    return a + b\n"
        res_range = replace_range(root, "calc.py", 1, 2, new_fn)
        assert res_range["success"] is True
        assert "-> int" in file_path.read_text()

        # 3. Aplicação de patch pontual
        res_patch = apply_patch(root, "calc.py", "return a + b", "return int(a + b)")
        assert res_patch["success"] is True
        assert "int(a + b)" in file_path.read_text()


# 6. Teste da Máquina de Estados Finita
def test_state_machine_transitions():
    from core.state_machine import DevelopmentStateMachine, DevelopmentState

    sm = DevelopmentStateMachine(max_repair_attempts=2)
    assert sm.current_state == DevelopmentState.IDLE

    # Transição válida
    sm.transition_to(DevelopmentState.DISCOVERY)
    assert sm.current_state == DevelopmentState.DISCOVERY

    sm.transition_to(DevelopmentState.PLANNING)
    sm.transition_to(DevelopmentState.IMPLEMENTING)
    sm.transition_to(DevelopmentState.TESTING)

    # Simular falha e reparação (tentativa 1)
    sm.transition_to(DevelopmentState.REPAIRING)
    assert sm.can_repair() is True

    sm.transition_to(DevelopmentState.TESTING)

    # Simular falha e reparação (tentativa 2)
    sm.transition_to(DevelopmentState.REPAIRING)

    # Simular falha e esgotamento de tentativas -> BLOCKED
    sm.transition_to(DevelopmentState.TESTING)
    sm.transition_to(DevelopmentState.REPAIRING)
    assert sm.current_state == DevelopmentState.BLOCKED


# 7. Teste de Memória do Projeto
def test_project_memory():
    from memory.project_memory import ProjectMemory

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        mem = ProjectMemory(root)

        # Registrar decisão
        mem.record_decision(
            decision_id="DEC-001",
            title="Uso de SQLite para testes",
            decision="Adotar SQLite in-memory para testes unitários",
            reason="Execução ultrarrápida sem depender de containers externos",
            rejected_alternatives=["PostgreSQL em Docker"],
            related_files=["tests/conftest.py"],
        )

        decisions_content = mem.read_decisions()
        assert "DEC-001" in decisions_content
        assert "SQLite in-memory" in decisions_content

        # Atualizar estado de tarefa
        mem.update_task_state("TASK-101", "COMPLETED", {"files": ["src/service.py"]})
        states = mem.get_task_states()
        assert "TASK-101" in states
        assert states["TASK-101"]["status"] == "COMPLETED"
