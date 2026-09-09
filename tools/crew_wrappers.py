from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Type

from pydantic import BaseModel, Field, PrivateAttr
from crewai.tools import BaseTool

from tools.filesystem import list_project_tree, read_file
from tools.search import search_code
from tools.patching import apply_patch
from tools.git import get_git_diff


class ListProjectTreeArgs(BaseModel):
    max_depth: int = Field(4, description="Profundidade máxima da busca na árvore")
    max_files: int = Field(150, description="Número máximo de arquivos a retornar")

class ListProjectTreeTool(BaseTool):
    name: str = "list_project_tree"
    description: str = "Lista a estrutura de diretórios e arquivos do projeto atual."
    args_schema: Type[BaseModel] = ListProjectTreeArgs
    _project_root: Path = PrivateAttr()

    def __init__(self, project_root: Path, **kwargs: Any):
        super().__init__(**kwargs)
        self._project_root = project_root

    def _run(self, max_depth: int = 4, max_files: int = 150) -> str:
        return list_project_tree(self._project_root, max_depth, max_files)


class ReadFileArgs(BaseModel):
    relative_path: str = Field(..., description="Caminho relativo do arquivo (ex: src/main.py)")
    start_line: int = Field(1, description="Linha inicial para leitura parcial")
    end_line: int | None = Field(None, description="Linha final para leitura parcial")

class ReadFileTool(BaseTool):
    name: str = "read_file"
    description: str = "Lê o conteúdo de um arquivo. Permite ler um trecho específico passando start_line e end_line."
    args_schema: Type[BaseModel] = ReadFileArgs
    _project_root: Path = PrivateAttr()

    def __init__(self, project_root: Path, **kwargs: Any):
        super().__init__(**kwargs)
        self._project_root = project_root

    def _run(self, relative_path: str, start_line: int = 1, end_line: int | None = None) -> str:
        return read_file(self._project_root, relative_path, start_line, end_line)


class SearchCodeArgs(BaseModel):
    query: str = Field(..., description="O texto, nome de função ou padrão para buscar")
    is_regex: bool = Field(False, description="Define se a busca usará expressão regular")

class SearchCodeTool(BaseTool):
    name: str = "search_code"
    description: str = "Busca no código-fonte por símbolos, funções ou strings."
    args_schema: Type[BaseModel] = SearchCodeArgs
    _project_root: Path = PrivateAttr()

    def __init__(self, project_root: Path, **kwargs: Any):
        super().__init__(**kwargs)
        self._project_root = project_root

    def _run(self, query: str, is_regex: bool = False) -> str:
        results = search_code(self._project_root, query, is_regex)
        if not results:
            return "Nenhuma ocorrência encontrada."
        return json.dumps(results, indent=2, ensure_ascii=False)


class ApplyPatchArgs(BaseModel):
    relative_path: str = Field(..., description="Caminho relativo do arquivo")
    target_content: str = Field(..., description="Trecho exato do código atual que será substituído. Deve bater 100% com o arquivo real.")
    replacement_content: str = Field(..., description="O novo código que substituirá o trecho alvo.")

class ApplyPatchTool(BaseTool):
    name: str = "apply_patch"
    description: str = (
        "Substitui um trecho exato de código em um arquivo. "
        "Use para modificações cirúrgicas. Exige que target_content seja uma correspondência exata."
    )
    args_schema: Type[BaseModel] = ApplyPatchArgs
    _project_root: Path = PrivateAttr()

    def __init__(self, project_root: Path, **kwargs: Any):
        super().__init__(**kwargs)
        self._project_root = project_root

    def _run(self, relative_path: str, target_content: str, replacement_content: str) -> str:
        # Atomicidade e limites de patch definidos: limitamos substituições muito grandes
        target_lines = len(target_content.splitlines())
        if target_lines > 150:
            return "Erro: O trecho alvo excede o limite de 150 linhas por patch. Divida a alteração."
            
        res = apply_patch(self._project_root, relative_path, target_content, replacement_content)
        if res.get("success"):
            return f"Patch aplicado com sucesso em {relative_path}!"
        return f"Falha no patch: {res.get('error')}"


class GitDiffArgs(BaseModel):
    pass

class GitDiffTool(BaseTool):
    name: str = "git_diff"
    description: str = "Mostra as alterações atuais feitas na working tree (git diff)."
    args_schema: Type[BaseModel] = GitDiffArgs
    _project_root: Path = PrivateAttr()

    def __init__(self, project_root: Path, **kwargs: Any):
        super().__init__(**kwargs)
        self._project_root = project_root

    def _run(self) -> str:
        return get_git_diff(self._project_root)
