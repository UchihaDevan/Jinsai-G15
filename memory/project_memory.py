"""Memória Persistente de Projeto (Decisões, Planos e Estado de Tarefas).

Gerencia a pasta `.jinsai/` na raiz de qualquer projeto atendido pelo Jinsai-G15:
- `.jinsai/decisions.md`: Decisões arquiteturais com justificativas e alternativas rejeitadas.
- `.jinsai/plan.yaml`: Plano estruturado com tarefas, arquivos e critérios de aceite.
- `.jinsai/task_state.json`: Rastreamento de tarefas concluídas, pendentes e bloqueadas.
- `.jinsai/execution_log.jsonl`: Histórico auditável de ações executadas.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


class ProjectMemory:
    """Interface de leitura e persistência da memória específica de um projeto."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.jinsai_dir = self.project_root / ".jinsai"
        self.decisions_file = self.jinsai_dir / "decisions.md"
        self.plan_file = self.jinsai_dir / "plan.yaml"
        self.task_state_file = self.jinsai_dir / "task_state.json"
        self.log_file = self.jinsai_dir / "execution_log.jsonl"
        self._ensure_storage()

    def _ensure_storage(self) -> None:
        """Garante a existência do diretório .jinsai, arquivos base e gitignore."""
        self.jinsai_dir.mkdir(parents=True, exist_ok=True)
        
        # Garante que a memória não suje o repositório Git
        gitignore_path = self.project_root / ".gitignore"
        gitignore_content = ""
        if gitignore_path.exists():
            gitignore_content = gitignore_path.read_text(encoding="utf-8")
        if ".jinsai/" not in gitignore_content:
            with open(gitignore_path, "a", encoding="utf-8") as f:
                f.write("\n# Jinsai Agent Memory\n.jinsai/\n")

        if not self.decisions_file.exists():
            self.decisions_file.write_text(
                "# Memória de Decisões Arquiteturais do Projeto\n\n"
                "Este arquivo registra decisões tomadas pelo Jinsai-G15 e seus motivos.\n\n",
                encoding="utf-8",
            )
        if not self.task_state_file.exists():
            self.task_state_file.write_text(json.dumps({"tasks": {}}, indent=2), encoding="utf-8")

    def record_decision(
        self,
        decision_id: str,
        title: str,
        decision: str,
        reason: str,
        rejected_alternatives: list[str] | None = None,
        related_files: list[str] | None = None,
    ) -> None:
        """Registra uma nova decisão arquitetural em decisions.md."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        rejections = "\n".join([f"- {alt}" for alt in (rejected_alternatives or ["Nenhuma documentada"])])
        files = "\n".join([f"  - `{f}`" for f in (related_files or ["Nenhum arquivo específico"])])

        entry = (
            f"## [{decision_id}] {title}\n\n"
            f"- **Data:** {now}\n"
            f"- **Decisão:** {decision}\n"
            f"- **Motivo:** {reason}\n"
            f"- **Alternativas Rejeitadas:**\n{rejections}\n"
            f"- **Arquivos Relacionados:**\n{files}\n\n"
            "---\n\n"
        )
        with open(self.decisions_file, "a", encoding="utf-8") as f:
            f.write(entry)

    def read_decisions(self) -> str:
        """Lê o histórico de decisões do projeto."""
        if self.decisions_file.exists():
            return self.decisions_file.read_text(encoding="utf-8")
        return ""

    def save_plan(self, plan_data: dict[str, Any]) -> None:
        """Salva o plano estruturado em YAML."""
        with open(self.plan_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(plan_data, f, sort_keys=False, allow_unicode=True)

    def load_plan(self) -> dict[str, Any] | None:
        """Carrega o plano estruturado se existir."""
        if not self.plan_file.exists():
            return None
        try:
            with open(self.plan_file, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception:
            return None

    def update_task_state(self, task_id: str, status: str, details: dict[str, Any] | None = None) -> None:
        """Atualiza o estado de uma tarefa (PENDING, IN_PROGRESS, TESTING, COMPLETED, BLOCKED)."""
        data = {"tasks": {}}
        if self.task_state_file.exists():
            try:
                data = json.loads(self.task_state_file.read_text(encoding="utf-8"))
            except Exception:
                data = {"tasks": {}}

        now = datetime.now(timezone.utc).isoformat()
        if task_id not in data["tasks"]:
            data["tasks"][task_id] = {"created_at": now}

        data["tasks"][task_id].update({
            "status": status,
            "updated_at": now,
            "details": details or {},
        })

        with open(self.task_state_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def get_task_states(self) -> dict[str, Any]:
        """Retorna o estado de todas as tarefas."""
        if self.task_state_file.exists():
            try:
                return json.loads(self.task_state_file.read_text(encoding="utf-8")).get("tasks", {})
            except Exception:
                return {}
        return {}

    def append_log(self, action: str, metadata: dict[str, Any] | None = None) -> None:
        """Registra uma linha no log auditável de execução."""
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "metadata": metadata or {},
        }
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
