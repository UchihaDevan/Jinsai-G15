#!/usr/bin/env python3
"""Orquestrador Autônomo do Jinsai-G15 v3.0.

Executa o ciclo completo de engenharia de software com acesso real e seguro
ao projeto: Discovery ➔ Planning ➔ Implementing ➔ Testing ➔ Reviewing ➔ Memory.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# Carregar variáveis de ambiente do .env
load_dotenv()

from core.vram_manager import VRAMManager
from core.rag_engine import LocalCodeRAG
from core.router import TaskRouter
from core.errors import (
    validate_project_root,
    verify_ollama_connection,
    verify_cloud_api_keys,
    InvalidProjectPathError,
)
from core.state_machine import DevelopmentStateMachine, DevelopmentState
from tools.filesystem import list_project_tree, read_project_config
from tools.git import create_checkpoint, get_git_diff, rollback_checkpoint
from tools.testing import run_unit_tests
from memory.project_memory import ProjectMemory

# Configuração de Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("jinsai.orchestrator")

BASE_DIR = Path(__file__).parent.resolve()
CONFIG_DIR = BASE_DIR / "config"


def load_yaml(file_path: Path) -> dict[str, Any]:
    """Carrega um arquivo YAML de configuração."""
    if not file_path.exists():
        logger.error("Arquivo de configuração não encontrado: %s", file_path)
        sys.exit(1)
    with open(file_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def build_crewai_llm(cfg: dict[str, Any]) -> Any:
    """Instancia o objeto LLM do CrewAI adequado para o provedor (Ollama, Anthropic, Google, etc.)."""
    from crewai import LLM

    provider = cfg.get("provider", "ollama")
    model_name = cfg.get("model", "qwen2.5-coder:3b")
    temperature = cfg.get("temperature", 0.2)

    if provider == "ollama":
        base_url = cfg.get("base_url", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
        num_ctx = cfg.get("num_ctx", 4096)
        return LLM(
            model=f"ollama/{model_name}",
            base_url=base_url,
            temperature=temperature,
            num_ctx=num_ctx,
        )
    elif provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY")
        return LLM(model=model_name, api_key=api_key, temperature=temperature)
    elif provider == "google":
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        return LLM(model=model_name, api_key=api_key, temperature=temperature)
    elif provider == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY")
        return LLM(model=model_name, api_key=api_key, base_url="https://api.deepseek.com", temperature=temperature)
    else:
        return LLM(model=model_name, temperature=temperature)


def execute_autonomous_cycle(
    user_prompt: str,
    preset_name: str,
    project_path: Path | None = None,
    skip_rag: bool = False,
) -> str:
    """Executa o ciclo autônomo de desenvolvimento (Nível 2/3)."""
    sm = DevelopmentStateMachine(max_repair_attempts=3)
    sm.transition_to(DevelopmentState.DISCOVERY)

    presets_data = load_yaml(CONFIG_DIR / "presets.yaml")
    agents_data = load_yaml(CONFIG_DIR / "agents.yaml")
    tasks_data = load_yaml(CONFIG_DIR / "tasks.yaml")

    presets = presets_data.get("presets", {})
    if preset_name not in presets:
        logger.warning("Perfil '%s' não reconhecido. Usando 'economy'.", preset_name)
        preset_name = "economy"

    preset = presets[preset_name]
    logger.info("--> Perfil Ativo: [%s] - %s", preset_name.upper(), preset.get("description", ""))

    # 1. Validação Prévia de Saúde
    if preset["dev_agent"]["provider"] == "ollama":
        if not verify_ollama_connection():
            logger.error("Serviço do Ollama não detectado em http://localhost:11434.")
            sys.exit(1)

    missing_key = verify_cloud_api_keys(preset["manager"]["provider"])
    if missing_key:
        logger.warning("Aviso: Chave de API %s não encontrada para o perfil %s.", missing_key, preset_name)

    # 2. Telemetria de VRAM
    vram_mgr = VRAMManager()
    vram_status = vram_mgr.get_gpu_vram_status()
    logger.info(
        "Telemetria RTX 3050: VRAM Usada: %d MiB | Livre: %d MiB / %d MiB",
        vram_status["used_mb"],
        vram_status["free_mb"],
        vram_status["total_mb"],
    )

    # 3. Discovery: Inspeção Real do Filesystem e Memória de Projeto
    project_root = validate_project_root(project_path)
    tree_context = "Nenhum diretório de projeto informado."
    config_context = ""
    memory_context = ""
    rag_context = ""
    project_mem = None

    if project_root:
        logger.info("Descobrindo topologia do projeto em: %s", project_root)
        tree_context = list_project_tree(project_root, max_depth=3, max_files=100)
        configs = read_project_config(project_root)
        if configs:
            config_context = "\n".join([f"=== {k} ===\n{v[:1500]}" for k, v in configs.items()])

        # Memória persistente do projeto (.jinsai/)
        project_mem = ProjectMemory(project_root)
        decisions = project_mem.read_decisions()
        if decisions.strip():
            memory_context = f"### Decisões Anteriores Registradas no Projeto:\n{decisions[-2000:]}\n"

        # RAG Local Complementar
        if not skip_rag:
            emb_model = preset.get("embedding", {}).get("model", "nomic-embed-text")
            rag = LocalCodeRAG(project_root=project_root, embedding_model=emb_model)
            rag.index_project()
            rag_context = rag.format_context_for_llm(user_prompt, n_results=4)

        # Checkpoint de Segurança antes de modificações
        import hashlib
        task_id_hash = hashlib.sha256(user_prompt.encode()).hexdigest()[:8]
        task_id = f"task_{task_id_hash}"
        checkpoint = create_checkpoint(project_root, task_id)
        logger.info("Checkpoint de segurança registrado: %s", checkpoint)

    # 4. Contexto Unificado para os Agentes
    unified_context = (
        f"### ÁRVORE E ESTRUTURA DO PROJETO:\n```\n{tree_context}\n```\n\n"
        f"{memory_context}\n"
        f"{('### CONFIGURAÇÕES DO PROJETO:\n' + config_context) if config_context else ''}\n"
        f"{rag_context}\n"
    )

    # 5. Planning
    sm.transition_to(DevelopmentState.PLANNING)
    from crewai import Agent, Crew, Process, Task
    from pydantic import BaseModel, Field
    from tools.crew_wrappers import ListProjectTreeTool, ReadFileTool, SearchCodeTool, ApplyPatchTool, GitDiffTool

    class TaskPlan(BaseModel):
        project: str = Field(description="Nome ou contexto do projeto")
        assumptions: list[str] = Field(description="Premissas assumidas pelo planejamento")
        constraints: list[str] = Field(description="Restrições de hardware, software ou regras")
        tasks: list[dict[str, str]] = Field(description="Lista de tarefas (id, description, files)")

    manager_llm = build_crewai_llm(preset["manager"])
    dev_llm = build_crewai_llm(preset["dev_agent"])

    manager_agent = Agent(
        role=agents_data["manager"]["role"],
        goal=agents_data["manager"]["goal"],
        backstory=agents_data["manager"]["backstory"],
        llm=manager_llm,
        verbose=True,
    )

    dev_tools = []
    if project_root:
        dev_tools = [
            ListProjectTreeTool(project_root=project_root),
            ReadFileTool(project_root=project_root),
            SearchCodeTool(project_root=project_root),
            ApplyPatchTool(project_root=project_root),
            GitDiffTool(project_root=project_root)
        ]

    dev_agent = Agent(
        role=agents_data["developer"]["role"],
        goal=agents_data["developer"]["goal"],
        backstory=agents_data["developer"]["backstory"],
        llm=dev_llm,
        tools=dev_tools,
        verbose=True,
    )

    plan_description = tasks_data["plan_task"]["description"].format(
        user_prompt=user_prompt,
        rag_context=unified_context,
    )
    plan_task = Task(
        description=plan_description,
        expected_output=tasks_data["plan_task"]["expected_output"],
        agent=manager_agent,
        output_pydantic=TaskPlan,
    )

    # 6. Implementing
    sm.transition_to(DevelopmentState.IMPLEMENTING)
    implement_description = tasks_data["implement_task"]["description"].format(
        architecture_plan="{plan_output}",
        rag_context=unified_context,
    )
    implement_task = Task(
        description=implement_description,
        expected_output=tasks_data["implement_task"]["expected_output"],
        agent=dev_agent,
        context=[plan_task],
    )

    crew = Crew(
        agents=[manager_agent, dev_agent],
        tasks=[plan_task, implement_task],
        process=Process.sequential,
        verbose=True,
    )

    logger.info("Iniciando execução dos agentes...")
    result = crew.kickoff()

    # 7. Testing & Validação Local
    sm.transition_to(DevelopmentState.TESTING)
    tests_passed = True
    diff_text = "Nenhuma alteração Git rastreada."
    
    if project_root:
        diff_text = get_git_diff(project_root)
        if diff_text and diff_text != "Nenhuma alteração Git rastreada.":
            logger.info("Diff após implementação:\n%s", diff_text)
        else:
            logger.info("Nenhum arquivo foi alterado pelo agente.")

        if (project_root / "tests").is_dir():
            logger.info("Executando suíte de testes unitários após implementação...")
            test_res = run_unit_tests(project_root, timeout=25.0)
            if test_res["passed"]:
                logger.info("Testes unitários aprovados com sucesso!")
                sm.transition_to(DevelopmentState.COMPLETED)
            else:
                logger.warning("Falha nos testes unitários: %s", test_res["stderr"] or test_res["stdout"][:300])
                tests_passed = False
                sm.transition_to(DevelopmentState.REPAIRING)
                logger.error("Repair loop será implementado em fase posterior. Marcando como BLOCKED.")
                sm.transition_to(DevelopmentState.BLOCKED)
        else:
            sm.transition_to(DevelopmentState.COMPLETED)
    else:
        sm.transition_to(DevelopmentState.COMPLETED)

    # 8. Atualização de Memória e Registro
    if project_mem:
        # Salva o plano validado
        if plan_task.output and getattr(plan_task.output, "pydantic", None):
            try:
                project_mem.save_plan(plan_task.output.pydantic.model_dump())
            except Exception as e:
                logger.error("Falha ao salvar o plano estruturado: %s", e)

        has_changes = diff_text and diff_text != "Nenhuma alteração Git rastreada."
        if tests_passed and has_changes:
            decision_msg = f"Implementação validada com alterações reais.\nResumo Diff:\n{diff_text[:1000]}"
        else:
            decision_msg = "Nenhum arquivo foi modificado com sucesso ou testes falharam."

        project_mem.record_decision(
            decision_id=f"DEC-{task_id_hash[:4]}",
            title=f"Execução: {user_prompt[:50]}...",
            decision=decision_msg,
            reason=f"Atendimento sob o perfil {preset_name}",
        )
        final_log_state = "TASK_COMPLETED" if tests_passed else "TASK_BLOCKED"
        project_mem.append_log(final_log_state, {"prompt": user_prompt, "preset": preset_name})

    logger.info("Ciclo autônomo concluído com estado final: %s", sm.current_state.value)
    return str(result)


def main() -> None:
    """Ponto de entrada via linha de comando."""
    parser = argparse.ArgumentParser(description="Jinsai-G15 v3.0 - Agente Autônomo de Engenharia de Software")
    parser.add_argument("--prompt", "-p", type=str, help="Instrução para a equipe de agentes")
    parser.add_argument(
        "--profile",
        type=str,
        default=os.getenv("JINSAI_DEFAULT_PROFILE", "economy"),
        choices=["offline", "economy", "precision", "deepseek_cloud", "moe_hybrid"],
        help="Perfil operacional (padrão: economy)",
    )
    parser.add_argument("--project", type=str, default=None, help="Caminho do projeto para inspeção e trabalho")
    parser.add_argument("--skip-rag", action="store_true", help="Ignora busca vetorial do RAG")
    parser.add_argument("--status", action="store_true", help="Exibe telemetria de VRAM e modelos ativos")

    args = parser.parse_args()

    if args.status:
        mgr = VRAMManager()
        vram = mgr.get_gpu_vram_status()
        models = mgr.get_running_ollama_models()
        print("\n=== TELEMETRIA HARDWARE (DELL G15 5520) ===")
        print(f"GPU: NVIDIA GeForce RTX 3050 Mobile")
        print(f"VRAM Total: {vram['total_mb']} MiB")
        print(f"VRAM Usada: {vram['used_mb']} MiB")
        print(f"VRAM Livre: {vram['free_mb']} MiB")
        print(f"Modelos Ativos no Ollama: {models if models else 'Nenhum (0 MiB em uso)'}\n")
        return

    prompt = args.prompt
    if not prompt:
        try:
            prompt = input("\n[Jinsai-G15 v3.0] Digite sua instrução para a equipe de agentes:\n> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nOperação cancelada.")
            return

    if not prompt:
        print("Nenhum prompt fornecido. Encerrando.")
        return

    project_dir = Path(args.project).resolve() if args.project else None
    result = execute_autonomous_cycle(
        user_prompt=prompt,
        preset_name=args.profile,
        project_path=project_dir,
        skip_rag=args.skip_rag,
    )

    print("\n================ RESULTADO FINAL ================\n")
    print(result)
    print("\n=================================================\n")


if __name__ == "__main__":
    main()
