"""Roteador de Tarefas em Dois Estágios (Dual-Stage Router).

Estágio 1: Heurísticas e Regex determinísticas (Custo zero de VRAM/tokens).
Estágio 2: Avaliação por LLM local ultraleve com descarregamento imediato.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("jinsai.router")


@dataclass
class RoutingDecision:
    """Decisão calculada de roteamento da tarefa."""
    is_complex: bool
    requires_rag: bool
    requires_cloud_manager: bool
    reason: str
    target_focus: str


class TaskRouter:
    """Roteia tarefas decidindo se necessitam de Arquiteto em nuvem, RAG ou execução local."""

    # Padrões que indicam tarefa puramente pontual ou local
    LOCAL_PATTERNS = [
        r"\b(crie|adicione|escreva)\s+(um|uma)?\s*(teste|unit test|docstring|coment[aá]rio)\b",
        r"\b(formate|lint|corrija o erro de sintaxe|valide|rode o teste)\b",
        r"\b(apenas|somente)\s+(fun[cç][aã]o|m[eé]todo|arquivo)\b",
    ]

    # Padrões que indicam planejamento arquitetural complexo
    COMPLEX_PATTERNS = [
        r"\b(arquitetura|reestruture|refatore todo|planeje|redesenhe)\b",
        r"\b(novo m[oó]dulo|sistema distribu[ií]do|microsservi[cç]o|pipeline completo)\b",
        r"\b(migra[cç][aã]o|seguran[cç]a|autentica[cç][aã]o oauth|integra[cç][aã]o)\b",
    ]

    # Padrões que exigem leitura do projeto via RAG
    RAG_TRIGGER_PATTERNS = [
        r"\b(no projeto|neste reposit[oó]rio|no arquivo|nos arquivos|com base no c[oó]digo)\b",
        r"\b(onde est[aá]|como funciona|onde fica|como [eé] implementado)\b",
        r"\b\w+\.(py|js|ts|tsx|jsx|html|css|json|yaml|sql)\b",
    ]

    def __init__(self, ollama_base_url: str = "http://localhost:11434") -> None:
        self.ollama_base_url = ollama_base_url.rstrip("/")

    def route(self, prompt: str, has_project_path: bool = False) -> RoutingDecision:
        """Executa a triagem da tarefa avaliando o texto do prompt."""
        prompt_lower = prompt.lower().strip()

        # Checagem de necessidade de RAG
        needs_rag = False
        if has_project_path:
            for pat in self.RAG_TRIGGER_PATTERNS:
                if re.search(pat, prompt_lower):
                    needs_rag = True
                    break

        # Checagem de complexidade arquitetural (Estágio 1 Determinístico)
        for pat in self.COMPLEX_PATTERNS:
            if re.search(pat, prompt_lower):
                return RoutingDecision(
                    is_complex=True,
                    requires_rag=needs_rag,
                    requires_cloud_manager=True,
                    reason=f"Gatilho arquitetural complexo identificado: '{pat}'",
                    target_focus="arquitetura",
                )

        # Checagem de tarefa local pontual
        for pat in self.LOCAL_PATTERNS:
            if re.search(pat, prompt_lower):
                return RoutingDecision(
                    is_complex=False,
                    requires_rag=needs_rag,
                    requires_cloud_manager=False,
                    reason=f"Gatilho de tarefa local identificado: '{pat}'",
                    target_focus="implementacao_local",
                )

        # Heurística de tamanho do prompt
        word_count = len(prompt.split())
        if word_count > 60:
            return RoutingDecision(
                is_complex=True,
                requires_rag=needs_rag,
                requires_cloud_manager=True,
                reason="Prompt detalhado com múltiplos requisitos (> 60 palavras)",
                target_focus="planejamento_multiplo",
            )

        # Padrão: fluxo balanceado padrão (Manager enxuto + Dev Local)
        return RoutingDecision(
            is_complex=False,
            requires_rag=needs_rag,
            requires_cloud_manager=True,
            reason="Tarefa padrão; encaminhada para planejamento e implementação local",
            target_focus="padrao",
        )
