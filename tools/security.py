"""Camada de Segurança, Sandboxing e Guardrails de Arquivos.

Garante que o agente nunca escape da raiz autorizada do projeto (anti-path-traversal)
e nunca leia ou modifique arquivos sensíveis contendo credenciais ou segredos.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from core.errors import SecurityViolationError

# Padrões de arquivos e diretórios estritamente bloqueados
BLOCKED_PATTERNS = [
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.crt",
    "id_rsa",
    "id_rsa.pub",
    "id_ed25519",
    "*.pfx",
    "credentials.json",
    "service_account.json",
    "credentials/*",
    "secrets/*",
    ".git/*",
    "**/.git/**",
]

# Comandos destrutivos terminantemente proibidos na execução segura
BLOCKED_SHELL_PATTERNS = [
    "rm -rf /",
    "rm -rf ~",
    "sudo ",
    "chmod -R",
    "chown -R",
    "curl | sh",
    "curl | bash",
    "wget | sh",
    "wget | bash",
    ":(){ :|:& };:",
    "drop database",
    "git push --force",
    "git push -f",
]


def is_path_blocked(relative_or_absolute_path: str | Path) -> bool:
    """Verifica se o caminho corresponde a algum padrão de arquivo sensível/bloqueado."""
    path_str = str(relative_or_absolute_path).replace("\\", "/")
    filename = Path(path_str).name

    for pattern in BLOCKED_PATTERNS:
        if fnmatch.fnmatch(filename, pattern):
            return True
        if fnmatch.fnmatch(path_str, pattern):
            return True
        if pattern.endswith("/*") and pattern[:-2] in path_str.split("/"):
            return True
    return False


def validate_safe_path(project_root: Path, target_path: str | Path) -> Path:
    """Valida se o caminho está dentro da raiz autorizada e fora de áreas sensíveis.

    Args:
        project_root: Raiz permitida do projeto.
        target_path: Caminho que o agente deseja acessar ou modificar.

    Returns:
        Path absoluto e resolvido seguro.

    Raises:
        SecurityViolationError: Se houver tentativa de escape ou acesso a arquivo bloqueado.
    """
    root_resolved = project_root.resolve()
    target = Path(target_path)

    # Se for relativo, resolve contra a raiz do projeto
    if not target.is_absolute():
        target = root_resolved / target

    target_resolved = target.resolve()

    # Checagem de confinamento na raiz (Anti Path Traversal)
    try:
        rel = target_resolved.relative_to(root_resolved)
    except ValueError:
        raise SecurityViolationError(
            f"Violação de Segurança: Tentativa de acessar caminho fora do projeto: '{target_resolved}'"
        )

    # Checagem de bloqueio de segredos
    if is_path_blocked(rel):
        raise SecurityViolationError(
            f"Violação de Segurança: Acesso proibido a arquivo sensível: '{rel}'"
        )

    return target_resolved


def is_command_safe(command: str) -> tuple[bool, str]:
    """Valida se o comando shell é seguro para execução.

    Returns:
        (True, "") se seguro, ou (False, motivo) se bloqueado.
    """
    cmd_lower = command.lower().strip()
    for bad in BLOCKED_SHELL_PATTERNS:
        if bad in cmd_lower:
            return False, f"Comando destrutivo ou proibido detectado: '{bad}'"
    return True, ""
