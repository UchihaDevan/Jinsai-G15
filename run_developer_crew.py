#!/usr/bin/env python3
"""Orquestrador Principal do Jinsai-G15 v2.2.

Executa fluxos híbridos e locais utilizando CrewAI, LiteLLM e Ollama,
com controle de VRAM da NVIDIA RTX 3050 e indexação vetorial via ChromaDB.
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

from core.memory_manager import VRAMManager
from core.rag_engine import LocalCodeRAG
from core.router import TaskRouter

# Configuração de Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("jinsai.main")

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
        # Formato Ollama no CrewAI / LiteLLM
        return LLM(
            model=f"ollama/{model_name}",
            base_url=base_url,
            temperature=temperature,
            num_ctx=num_ctx,
        )
    elif provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY não encontrada no ambiente.")
        return LLM(
            model=model_name,
            api_key=api_key,
            temperature=temperature,
        )
    elif provider == "google":
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            logger.warning("GEMINI_API_KEY ou GOOGLE_API_KEY não encontrada no ambiente.")
        return LLM(
            model=model_name,
            api_key=api_key,
            temperature=temperature,
        )
    elif provider == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY")
        base_url = "https://api.deepseek.com"
        return LLM(
            model=model_name,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
        )
    else:
        # Fallback genérico para LiteLLM
        return LLM(model=model_name, temperature=temperature)


def execute_crew(
    user_prompt: str,
    preset_name: str,
    project_path: Path | None = None,
    skip_rag: bool = False,
) -> str:
    """Executa a orquestração de agentes para o prompt fornecido."""
    from crewai import Agent, Crew, Process, Task

    presets_data = load_yaml(CONFIG_DIR / "presets.yaml")
    agents_data = load_yaml(CONFIG_DIR / "agents.yaml")
    tasks_data = load_yaml(CONFIG_DIR / "tasks.yaml")

    presets = presets_data.get("presets", {})
    if preset_name not in presets:
        logger.warning("Perfil '%s' não encontrado. Usando 'economy'.", preset_name)
        preset_name = "economy"

    preset = presets[preset_name]
    logger.info("--> Ativando Perfil: [%s] - %s", preset_name.upper(), preset.get("description", ""))

    # 1. Gerenciamento de VRAM
    vram_mgr = VRAMManager()
    vram_status = vram_mgr.get_gpu_vram_status()
    logger.info(
        "Telemetria RTX 3050: VRAM Usada: %d MiB | Livre: %d MiB / %d MiB",
        vram_status["used_mb"],
        vram_status["free_mb"],
        vram_status["total_mb"],
    )

    # 2. Triagem e Roteamento
    router = TaskRouter()
    decision = router.route(user_prompt, has_project_path=bool(project_path and not skip_rag))
    logger.info("Decisão de Roteamento: %s (Complexo=%s, RAG=%s)", decision.reason, decision.is_complex, decision.requires_rag)

    # 3. Contexto do RAG Local (se aplicável)
    rag_context = "Nenhum diretório de projeto especificado para indexação."
    if decision.requires_rag and project_path:
        emb_model = preset.get("embedding", {}).get("model", "nomic-embed-text")
        logger.info("Indexando projeto com RAG Local via '%s'...", emb_model)
        rag = LocalCodeRAG(project_root=project_path, embedding_model=emb_model)
        rag.index_project()
        rag_context = rag.format_context_for_llm(user_prompt, n_results=4)
        logger.info("Contexto semântico extraído com sucesso do projeto.")

    # 4. Configuração dos Modelos LLM
    manager_llm = build_crewai_llm(preset["manager"])
    dev_llm = build_crewai_llm(preset["dev_agent"])

    # 5. Instanciação dos Agentes
    manager_agent = Agent(
        role=agents_data["manager"]["role"],
        goal=agents_data["manager"]["goal"],
        backstory=agents_data["manager"]["backstory"],
        llm=manager_llm,
        verbose=True,
    )

    dev_agent = Agent(
        role=agents_data["developer"]["role"],
        goal=agents_data["developer"]["goal"],
        backstory=agents_data["developer"]["backstory"],
        llm=dev_llm,
        verbose=True,
    )

    # 6. Criação das Tarefas
    plan_description = tasks_data["plan_task"]["description"].format(
        user_prompt=user_prompt,
        rag_context=rag_context,
    )
    plan_task = Task(
        description=plan_description,
        expected_output=tasks_data["plan_task"]["expected_output"],
        agent=manager_agent,
    )

    implement_description = tasks_data["implement_task"]["description"].format(
        architecture_plan="{plan_output}",
        rag_context=rag_context,
    )
    implement_task = Task(
        description=implement_description,
        expected_output=tasks_data["implement_task"]["expected_output"],
        agent=dev_agent,
        context=[plan_task],
    )

    # 7. Execução do Crew
    crew = Crew(
        agents=[manager_agent, dev_agent],
        tasks=[plan_task, implement_task],
        process=Process.sequential,
        verbose=True,
    )

    logger.info("Iniciando pipeline de agentes...")
    result = crew.kickoff()
    logger.info("Pipeline concluído com sucesso!")
    return str(result)


def main() -> None:
    """Ponto de entrada via linha de comando."""
    parser = argparse.ArgumentParser(description="Jinsai-G15 v2.2 - Agente Hierárquico Local-First")
    parser.add_argument(
        "--prompt", "-p",
        type=str,
        help="Instrução ou tarefa a ser executada pelo sistema",
    )
    parser.add_argument(
        "--profile",
        type=str,
        default=os.getenv("JINSAI_DEFAULT_PROFILE", "economy"),
        choices=["offline", "economy", "precision", "deepseek_cloud", "moe_hybrid"],
        help="Perfil operacional de modelos (padrão: economy)",
    )
    parser.add_argument(
        "--project",
        type=str,
        default=None,
        help="Caminho para a pasta do projeto a ser indexada via RAG",
    )
    parser.add_argument(
        "--skip-rag",
        action="store_true",
        help="Ignora busca vetorial mesmo se projeto for especificado",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Mostra telemetria de VRAM e modelos ativos no Ollama",
    )

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
            prompt = input("\n[Jinsai-G15] Digite sua instrução para a equipe de agentes:\n> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nOperação cancelada.")
            return

    if not prompt:
        print("Nenhum prompt fornecido. Encerrando.")
        return

    project_dir = Path(args.project).resolve() if args.project else None
    result = execute_crew(
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
