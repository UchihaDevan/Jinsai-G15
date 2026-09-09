"""Máquina de Estados Finita para Ciclo de Desenvolvimento Autônomo.

Estados:
  DISCOVERY ➔ PLANNING ➔ IMPLEMENTING ➔ TESTING ➔ REPAIRING ➔ REVIEWING ➔ COMPLETED / BLOCKED
"""

from __future__ import annotations

from enum import Enum


class DevelopmentState(str, Enum):
    IDLE = "IDLE"
    DISCOVERY = "DISCOVERY"
    PLANNING = "PLANNING"
    IMPLEMENTING = "IMPLEMENTING"
    TESTING = "TESTING"
    REPAIRING = "REPAIRING"
    REVIEWING = "REVIEWING"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"


class DevelopmentStateMachine:
    """Controla transições válidas de estado e limites de tentativas de reparação."""

    VALID_TRANSITIONS = {
        DevelopmentState.IDLE: {DevelopmentState.DISCOVERY},
        DevelopmentState.DISCOVERY: {DevelopmentState.PLANNING, DevelopmentState.BLOCKED},
        DevelopmentState.PLANNING: {DevelopmentState.IMPLEMENTING, DevelopmentState.BLOCKED},
        DevelopmentState.IMPLEMENTING: {DevelopmentState.TESTING, DevelopmentState.BLOCKED},
        DevelopmentState.TESTING: {DevelopmentState.REVIEWING, DevelopmentState.REPAIRING, DevelopmentState.COMPLETED},
        DevelopmentState.REPAIRING: {DevelopmentState.TESTING, DevelopmentState.BLOCKED},
        DevelopmentState.REVIEWING: {DevelopmentState.COMPLETED, DevelopmentState.REPAIRING, DevelopmentState.BLOCKED},
        DevelopmentState.COMPLETED: {DevelopmentState.IDLE},
        DevelopmentState.BLOCKED: {DevelopmentState.IDLE},
    }

    def __init__(self, max_repair_attempts: int = 3) -> None:
        self.current_state = DevelopmentState.IDLE
        self.max_repair_attempts = max_repair_attempts
        self.repair_attempts = 0
        self.history: list[DevelopmentState] = [self.current_state]

    def transition_to(self, new_state: DevelopmentState) -> None:
        """Transiciona para um novo estado validando regras do ciclo."""
        allowed = self.VALID_TRANSITIONS.get(self.current_state, set())
        if new_state not in allowed:
            raise ValueError(f"Transição inválida de {self.current_state.value} para {new_state.value}.")

        if new_state == DevelopmentState.REPAIRING:
            self.repair_attempts += 1
            if self.repair_attempts > self.max_repair_attempts:
                # Esgotou tentativas de reparo; transiciona para BLOCKED
                self.current_state = DevelopmentState.BLOCKED
                self.history.append(self.current_state)
                return

        self.current_state = new_state
        self.history.append(new_state)

    def can_repair(self) -> bool:
        """Retorna se ainda restam tentativas de correção."""
        return self.repair_attempts < self.max_repair_attempts
