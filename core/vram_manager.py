"""Gerenciador de Ciclo de Vida de VRAM e Ollama para NVIDIA RTX 3050 (4GB).

Projetado para o Dell G15 5520 executando BigLinux com CUDA 13.x.
Monitora consumo de VRAM em tempo real e orquestra o carregamento/descarregamento
de modelos locais para evitar estouro dos 4096 MiB.
"""

from __future__ import annotations

import contextlib
import logging
import shutil
import subprocess
from typing import Generator
import httpx

logger = logging.getLogger("jinsai.vram_manager")


class VRAMManager:
    """Gerencia o uso de VRAM da GPU NVIDIA e os modelos ativos no Ollama."""

    def __init__(
        self,
        ollama_base_url: str = "http://localhost:11434",
        max_vram_mb: int = 4096,
        warning_threshold_mb: int = 3600,
    ) -> None:
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self.max_vram_mb = max_vram_mb
        self.warning_threshold_mb = warning_threshold_mb

    def get_gpu_vram_status(self) -> dict[str, int]:
        """Obtém status de VRAM da GPU NVIDIA via nvidia-smi.

        Returns:
            dict com used_mb, total_mb e free_mb.
        """
        if not shutil.which("nvidia-smi"):
            logger.warning("nvidia-smi não encontrado no PATH.")
            return {"used_mb": 0, "total_mb": self.max_vram_mb, "free_mb": self.max_vram_mb}

        try:
            cmd = [
                "nvidia-smi",
                "--query-gpu=memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            line = result.stdout.strip().split("\n")[0]
            used_str, total_str = [x.strip() for x in line.split(",")]
            used_mb = int(used_str)
            total_mb = int(total_str)
            return {
                "used_mb": used_mb,
                "total_mb": total_mb,
                "free_mb": max(0, total_mb - used_mb),
            }
        except Exception as exc:
            logger.warning("Falha ao consultar nvidia-smi: %s", exc)
            return {"used_mb": 0, "total_mb": self.max_vram_mb, "free_mb": self.max_vram_mb}

    def get_running_ollama_models(self) -> list[str]:
        """Consulta os modelos carregados atualmente na memória/VRAM pelo Ollama.

        Returns:
            Lista de nomes de modelos em execução.
        """
        try:
            url = f"{self.ollama_base_url}/api/ps"
            response = httpx.get(url, timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                return [m.get("name") or m.get("model") for m in models if m]
        except Exception as exc:
            logger.debug("Ollama /api/ps indisponível ou inacessível: %s", exc)
        return []

    def unload_model(self, model_name: str) -> bool:
        """Descarrega imediatamente um modelo específico da VRAM definindo keep_alive: 0.

        Args:
            model_name: Nome do modelo (ex: 'qwen2.5-coder:3b' ou 'nomic-embed-text').

        Returns:
            True se descarregado com sucesso.
        """
        try:
            url = f"{self.ollama_base_url}/api/generate"
            payload = {"model": model_name, "keep_alive": 0}
            response = httpx.post(url, json=payload, timeout=10.0)
            if response.status_code == 200:
                logger.info("Modelo '%s' descarregado da VRAM com sucesso.", model_name)
                return True
        except Exception as exc:
            logger.error("Erro ao descarregar modelo '%s': %s", model_name, exc)
        return False

    def unload_all(self) -> list[str]:
        """Descarrega todos os modelos em execução para liberar 100% da VRAM da RTX 3050."""
        running = self.get_running_ollama_models()
        unloaded = []
        for model in running:
            if model and self.unload_model(model):
                unloaded.append(model)
        return unloaded

    def warm_up_model(self, model_name: str, keep_alive: str = "5m") -> bool:
        """Pré-aquece um modelo na VRAM mantendo-o ativo pelo tempo especificado."""
        try:
            url = f"{self.ollama_base_url}/api/generate"
            payload = {
                "model": model_name,
                "prompt": "",
                "keep_alive": keep_alive,
            }
            response = httpx.post(url, json=payload, timeout=15.0)
            return response.status_code == 200
        except Exception as exc:
            logger.warning("Não foi possível pré-aquecer '%s': %s", model_name, exc)
            return False

    @contextlib.contextmanager
    def scoped_model(self, model_name: str, keep_alive_after: str | None = None) -> Generator[str, None, None]:
        """Context Manager para garantir isolamento e higiene de VRAM.

        Antes de entrar no bloco, verifica a VRAM. Se outro modelo estiver ativo,
        descarrega-o para que este modelo tenha os 4096 MiB livres.
        Ao sair do bloco, descarrega o modelo ou define o keep_alive estipulado.
        """
        running = self.get_running_ollama_models()
        for active in running:
            if active and active != model_name:
                logger.info("Descarregando modelo concorrente '%s' para liberar VRAM.", active)
                self.unload_model(active)

        vram = self.get_gpu_vram_status()
        logger.info(
            "Alocando '%s' na GPU. VRAM Usada: %d/%d MiB (Livre: %d MiB).",
            model_name,
            vram["used_mb"],
            vram["total_mb"],
            vram["free_mb"],
        )

        try:
            yield model_name
        finally:
            if keep_alive_after is not None:
                self.warm_up_model(model_name, keep_alive=keep_alive_after)
            else:
                self.unload_model(model_name)
