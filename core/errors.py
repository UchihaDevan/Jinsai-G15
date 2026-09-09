"""Tratamento de Exceções e Verificações de Saúde do Sistema Jinsai-G15.

Provê classes de erro especializadas e funções de verificação prévia para
garantir falhas rápidas (fail-fast) com diagnósticos claros ao desenvolvedor.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("jinsai.errors")


class JinsaiError(Exception):
    """Exceção base para todos os erros do Jinsai."""


class OllamaUnavailableError(JinsaiError):
    """Lançada quando o serviço Ollama não está rodando."""


class ModelNotFoundError(JinsaiError):
    """Lançada quando um modelo requerido não está instalado no Ollama."""


class MissingAPIKeyError(JinsaiError):
    """Lançada quando uma chave de API necessária não está configurada."""


class InvalidProjectPathError(JinsaiError):
    """Lançada quando o caminho do projeto é inválido ou inexistente."""


class SecurityViolationError(JinsaiError):
    """Lançada quando uma ação do agente tenta violar as regras de sandbox do projeto."""


class CheckpointError(JinsaiError):
    """Lançada quando ocorre falha ao criar ou reverter um checkpoint."""


def verify_ollama_connection(base_url: str = "http://localhost:11434", timeout: float = 3.0) -> bool:
    """Verifica se o servidor Ollama está acessível."""
    try:
        res = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=timeout)
        return res.status_code == 200
    except Exception as exc:
        logger.debug("Falha na conexão com Ollama: %s", exc)
        return False


def verify_model_installed(model_name: str, base_url: str = "http://localhost:11434") -> bool:
    """Verifica se um modelo específico está presente no Ollama."""
    try:
        res = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=5.0)
        if res.status_code == 200:
            models = res.json().get("models", [])
            installed = [m.get("name", "").split(":")[0] for m in models]
            installed_full = [m.get("name", "") for m in models]
            target_clean = model_name.split(":")[0]
            return model_name in installed_full or target_clean in installed
    except Exception as exc:
        logger.debug("Erro ao verificar modelo '%s': %s", model_name, exc)
    return False


def verify_cloud_api_keys(provider: str) -> str | None:
    """Verifica se a chave de API exigida para o provedor em nuvem está configurada.

    Returns:
        None se a chave estiver presente, ou o nome da variável ausente.
    """
    if provider == "anthropic":
        if not os.getenv("ANTHROPIC_API_KEY"):
            return "ANTHROPIC_API_KEY"
    elif provider == "google":
        if not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
            return "GEMINI_API_KEY (ou GOOGLE_API_KEY)"
    elif provider == "deepseek":
        if not os.getenv("DEEPSEEK_API_KEY"):
            return "DEEPSEEK_API_KEY"
    elif provider == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            return "OPENAI_API_KEY"
    return None


def validate_project_root(project_path: str | Path | None) -> Path | None:
    """Valida se o caminho do projeto existe e é um diretório acessível."""
    if project_path is None:
        return None
    path = Path(project_path).resolve()
    if not path.exists():
        raise InvalidProjectPathError(f"O caminho do projeto '{path}' não existe.")
    if not path.is_dir():
        raise InvalidProjectPathError(f"O caminho do projeto '{path}' não é um diretório válido.")
    return path
