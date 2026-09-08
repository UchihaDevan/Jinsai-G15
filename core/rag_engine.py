"""Motor RAG Local Incremental com ChromaDB e Embeddings do Ollama.

Aproveita os 16 threads do Intel Core i5-12500H para leitura, filtragem e hashing SHA-256,
mantendo indexação incremental para evitar retrabalho de GPU.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("jinsai.rag_engine")

# Diretórios e extensões a ignorar
IGNORED_DIRS = {
    ".git",
    "node_modules",
    "venv",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "dist",
    "build",
    ".gemini",
    ".idea",
    ".vscode",
}

SUPPORTED_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".json",
    ".yaml",
    ".yml",
    ".md",
    ".html",
    ".css",
    ".sh",
    ".bash",
    ".sql",
    ".c",
    ".cpp",
    ".h",
}


def calculate_sha256(file_path: Path) -> str:
    """Calcula o hash SHA-256 de um arquivo."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class CodeChunk:
    """Representa um pedaço sintático de código indexado."""

    def __init__(
        self,
        file_path: str,
        start_line: int,
        end_line: int,
        content: str,
        chunk_id: str,
    ) -> None:
        self.file_path = file_path
        self.start_line = start_line
        self.end_line = end_line
        self.content = content
        self.chunk_id = chunk_id

    def to_metadata(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
        }


class LocalCodeRAG:
    """Gerencia indexação de arquivos e recuperação semântica usando ChromaDB e Ollama."""

    def __init__(
        self,
        project_root: str | Path,
        persist_dir: str | Path | None = None,
        embedding_model: str = "nomic-embed-text",
        ollama_base_url: str = "http://localhost:11434",
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.persist_dir = (
            Path(persist_dir)
            if persist_dir
            else self.project_root / ".jinsai_chroma"
        )
        self.embedding_model = embedding_model
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self.cache_file = self.project_root / ".jinsai_cache.json"

        self._collection = None
        self._init_chromadb()

    def _init_chromadb(self) -> None:
        """Inicializa o cliente ChromaDB persistente."""
        try:
            import chromadb

            self.chroma_client = chromadb.PersistentClient(path=str(self.persist_dir))
            # Nome da coleção baseado no nome da pasta
            collection_name = f"jinsai_{self.project_root.name.lower().replace('-', '_')}"
            self._collection = self.chroma_client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("ChromaDB inicializado em: %s", self.persist_dir)
        except ImportError:
            logger.warning("chromadb não instalado. Busca semântica operará em modo fallback.")
            self.chroma_client = None
            self._collection = None

    def get_embedding(self, text: str) -> list[float]:
        """Gera embedding vetorial usando a API do Ollama."""
        url = f"{self.ollama_base_url}/api/embeddings"
        payload = {"model": self.embedding_model, "prompt": text}
        try:
            res = httpx.post(url, json=payload, timeout=30.0)
            res.raise_for_status()
            return res.json().get("embedding", [])
        except Exception as exc:
            logger.error("Falha ao gerar embedding com '%s': %s", self.embedding_model, exc)
            return []

    def _chunk_file(self, file_path: Path, max_lines: int = 60, overlap: int = 10) -> list[CodeChunk]:
        """Quebra um arquivo de código em trechos mantendo numeração de linhas."""
        chunks: list[CodeChunk] = []
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception as exc:
            logger.debug("Não foi possível ler '%s': %s", file_path, exc)
            return []

        rel_path = str(file_path.relative_to(self.project_root))
        total_lines = len(lines)

        if total_lines == 0:
            return []

        # Se for arquivo curto, indexa tudo de uma vez
        if total_lines <= max_lines:
            content = "".join(lines)
            chunk_id = f"{rel_path}:1-{total_lines}"
            return [CodeChunk(rel_path, 1, total_lines, content, chunk_id)]

        idx = 0
        while idx < total_lines:
            end_idx = min(idx + max_lines, total_lines)
            chunk_lines = lines[idx:end_idx]
            content = "".join(chunk_lines)
            start_num = idx + 1
            end_num = end_idx
            chunk_id = f"{rel_path}:{start_num}-{end_num}"
            chunks.append(CodeChunk(rel_path, start_num, end_num, content, chunk_id))

            if end_idx >= total_lines:
                break
            idx += max_lines - overlap

        return chunks

    def index_project(self) -> dict[str, int]:
        """Varre o projeto de forma incremental e indexa apenas arquivos modificados."""
        if not self._collection:
            logger.warning("ChromaDB não configurado, pulando indexação.")
            return {"indexed": 0, "skipped": 0}

        # Carregar cache de hashes anterior
        cache: dict[str, str] = {}
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    cache = json.load(f)
            except Exception:
                cache = {}

        current_cache: dict[str, str] = {}
        files_to_index: list[Path] = []
        skipped_count = 0

        for root, dirs, files in os.walk(self.project_root):
            # Ignorar diretórios excluídos
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]

            for file_name in files:
                ext = Path(file_name).suffix.lower()
                if ext in SUPPORTED_EXTENSIONS:
                    full_path = Path(root) / file_name
                    rel_str = str(full_path.relative_to(self.project_root))
                    file_hash = calculate_sha256(full_path)
                    current_cache[rel_str] = file_hash

                    # Verificar se mudou
                    if cache.get(rel_str) == file_hash:
                        skipped_count += 1
                    else:
                        files_to_index.append(full_path)

        indexed_count = 0
        for fpath in files_to_index:
            rel_str = str(fpath.relative_to(self.project_root))
            chunks = self._chunk_file(fpath)
            if not chunks:
                continue

            ids: list[str] = []
            docs: list[str] = []
            metas: list[dict[str, Any]] = []
            embeddings: list[list[float]] = []

            for chunk in chunks:
                emb = self.get_embedding(chunk.content)
                if emb:
                    ids.append(chunk.chunk_id)
                    docs.append(chunk.content)
                    metas.append(chunk.to_metadata())
                    embeddings.append(emb)

            if ids:
                self._collection.upsert(
                    ids=ids,
                    documents=docs,
                    metadatas=metas,
                    embeddings=embeddings,
                )
                indexed_count += 1

        # Salvar cache atualizado
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump(current_cache, f, indent=2)

        logger.info(
            "Indexação concluída: %d arquivos indexados/atualizados, %d inalterados.",
            indexed_count,
            skipped_count,
        )
        return {"indexed": indexed_count, "skipped": skipped_count}

    def query_relevant_chunks(self, query: str, n_results: int = 5) -> list[dict[str, Any]]:
        """Pesquisa semântica para recuperar trechos mais pertinentes."""
        if not self._collection:
            return []

        query_emb = self.get_embedding(query)
        if not query_emb:
            return []

        try:
            results = self._collection.query(
                query_embeddings=[query_emb],
                n_results=n_results,
            )

            retrieved = []
            if results and results.get("documents"):
                docs = results["documents"][0]
                metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(docs)
                ids = results["ids"][0] if results.get("ids") else [""] * len(docs)

                for doc, meta, cid in zip(docs, metas, ids):
                    retrieved.append({
                        "id": cid,
                        "file_path": meta.get("file_path", "desconhecido"),
                        "start_line": meta.get("start_line", 0),
                        "end_line": meta.get("end_line", 0),
                        "content": doc,
                    })
            return retrieved
        except Exception as exc:
            logger.error("Erro na busca semântica: %s", exc)
            return []

    def format_context_for_llm(self, query: str, n_results: int = 4) -> str:
        """Formata os chunks recuperados em Markdown claro para injeção no prompt do LLM."""
        chunks = self.query_relevant_chunks(query, n_results=n_results)
        if not chunks:
            return "Nenhum trecho de código indexado relevante encontrado."

        output_parts = ["### Trechos de Código Relevantes do Projeto (RAG Local):\n"]
        for c in chunks:
            output_parts.append(
                f"**Arquivo:** `{c['file_path']}` (Linhas {c['start_line']}-{c['end_line']})\n"
                f"```\n{c['content']}\n```\n"
            )
        return "\n".join(output_parts)
