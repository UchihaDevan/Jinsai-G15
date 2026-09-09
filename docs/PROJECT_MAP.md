# Mapa Técnico e Grafo de Dependências do Projeto: Jinsai-G15 v3.1

> **Data da Auditoria Estática:** 2026-09-09  
> **Hash/Commit de Referência:** Working Tree Local (`/home/devan/Documentos/Jinsai-G15/`)  
> **Ambiente Base:** Dell G15 5520 (Intel Core i5-12500H 16 threads, 16GB RAM, NVIDIA RTX 3050 4GB VRAM, BigLinux 6.18)  
> **Versão Estruturada (Machine-Readable):** [`docs/PROJECT_MAP.generated.json`](file:///home/devan/Documentos/Jinsai-G15/docs/PROJECT_MAP.generated.json)  
> **Regra de Ouro:** *Este mapa serve como primeira camada de contexto; nunca altere código sem busca estática prévia dos símbolos e execução da suíte de testes.*

---

## 1. Decomposição do Nível de Confiança

Para eliminar classificações unidimensionais ou otimistas, cada módulo é avaliado em 4 dimensões independentes:

| Dimensão | Critério de Avaliação |
| :--- | :--- |
| **Estrutural** | Símbolos, assinaturas, imports e arquivos foram localizados e conferidos no código-fonte. |
| **Comportamental** | A lógica interna e as ramificações de erro foram comprovadas por testes automatizados (`tests/test_base.py`). |
| **Runtime** | A execução real contra binários (`nvidia-smi`, `git`, `rg`, `pytest`) ou sockets de rede ocorreu com sucesso. |
| **Contratual** | Os formatos de entrada/saída e todos os consumidores diretos/indiretos foram confirmados de ponta a ponta. |

---

## 2. Grafo de Chamadas Símbolo a Símbolo (Call Graph com Evidências)

### 2.1. Quem Chama Quem (Evidências de Chamada Real)

```
run_developer_crew.py:
  │
  ├── [L113] ──> core.errors.verify_ollama_connection()
  ├── [L117] ──> core.errors.verify_cloud_api_keys(provider)
  ├── [L123] ──> core.vram_manager.VRAMManager.get_gpu_vram_status()
  ├── [L132] ──> core.errors.validate_project_root(project_path)
  ├── [L141] ──> tools.filesystem.list_project_tree(project_root)
  ├── [L142] ──> tools.filesystem.read_project_config(project_root)
  ├── [L147] ──> memory.project_memory.ProjectMemory(project_root)
  │                └── [L148] ──> read_decisions()
  ├── [L155] ──> core.rag_engine.LocalCodeRAG(project_root, embedding_model)
  │                ├── [L156] ──> index_project()
  │                └── [L157] ──> format_context_for_llm(user_prompt)
  ├── [L161] ──> tools.git.create_checkpoint(project_root, task_id)
  ├── [L173] ──> core.state_machine.DevelopmentStateMachine.transition_to(PLANNING)
  ├── [L176] ──> build_crewai_llm(preset['manager'])
  ├── [L177] ──> build_crewai_llm(preset['dev_agent'])
  ├── [L206] ──> core.state_machine.DevelopmentStateMachine.transition_to(IMPLEMENTING)
  ├── [L226] ──> crew.kickoff()  (Execução CrewAI)
  ├── [L229] ──> core.state_machine.DevelopmentStateMachine.transition_to(TESTING)
  ├── [L232] ──> tools.testing.run_unit_tests(project_root)
  │                ├── [Se passou: L235] ──> transition_to(COMPLETED)
  │                └── [Se falhou: L238] ──> transition_to(REPAIRING)
  └── [L244] ──> memory.project_memory.ProjectMemory.record_decision()
  └── [L250] ──> memory.project_memory.ProjectMemory.append_log()
```

### 2.2. Consumidores Reversos de Ferramentas de Segurança

```
tools.security.validate_safe_path:
  ├── Chamada por tools.filesystem.read_file()              [tools/filesystem.py:78]
  ├── Chamada por tools.filesystem.get_file_metadata()       [tools/filesystem.py:106]
  ├── Chamada por tools.patching.create_file()               [tools/patching.py:18]
  ├── Chamada por tools.patching.replace_range()             [tools/patching.py:38]
  ├── Chamada por tools.patching.apply_patch()               [tools/patching.py:79]
  ├── Chamada por tools.patching.delete_file()               [tools/patching.py:110]
  ├── Chamada por tools.testing.run_syntax_check()           [tools/testing.py:19]
  ├── Chamada por tools.testing.run_unit_tests()             [tools/testing.py:47]
  └── Chamada por tests.test_base.test_security_guardrails() [tests/test_base.py:78]

tools.security.is_path_blocked:
  ├── Chamada internamente por tools.security.validate_safe_path() [tools/security.py:79]
  ├── Chamada por tools.search.search_code()                       [tools/search.py:56, 74]
  └── Chamada por tests.test_base.test_security_guardrails()       [tests/test_base.py:87]
```

---

## 3. Auditoria de Código Ocioso e Desconexões Arquiteturais

A inspeção estática detalhada revelou **símbolos importados mas nunca invocados** (`dead imports`) e **ferramentas implementadas que ainda não estão amarradas ao fluxo do agente** (`unconnected tools`).

### 3.1. Dead Imports em `run_developer_crew.py`
1. **`from core.router import TaskRouter` [Linha 25]:**  
   * *Status:* Ocioso. A lógica de transição foi assumida diretamente pela máquina de estados na linha 89. A classe `TaskRouter` não é instanciada nem chamada no pipeline.
2. **`from core.errors import InvalidProjectPathError` [Linha 30]:**  
   * *Status:* Ocioso. Nenhuma cláusula `try/except InvalidProjectPathError` existe no arquivo.
3. **`from tools.git import get_git_diff, rollback_checkpoint` [Linha 34]:**  
   * *Status:* Ocioso e Crítico. O orquestrador importa ambas as funções, mas na linha 238, quando `test_res['passed']` é falso, **`rollback_checkpoint()` NUNCA é chamado**! O sistema apenas registra um aviso e transiciona para `REPAIRING`, sem reverter o estado.

### 3.2. Dead Imports em `tools/testing.py`
1. **`from tools.security import is_command_safe` [Linha 14]:**  
   * *Status:* Ocioso. A função é importada no topo do arquivo, mas o corpo de `run_unit_tests` monta o comando `cmd` diretamente sem chamar `is_command_safe(cmd)`.

### 3.3. Ferramentas Desconectadas do Agente (`Unconnected Tools`)
As seguintes ferramentas foram implementadas e possuem testes unitários, mas **NÃO estão atribuídas ao parâmetro `tools=[...]` do `dev_agent` ou `manager_agent` em `run_developer_crew.py`**:
* `tools.patching.create_file`
* `tools.patching.replace_range`
* `tools.patching.apply_patch`
* `tools.patching.delete_file`
* `tools.filesystem.read_file`
* `tools.filesystem.get_file_metadata`
* `tools.search.search_code`

> **Impacto Arquitetural:** O `dev_agent` atualmente opera apenas como gerador textual. O código gerado é impresso no console ou passado via stdout, e não gravado diretamente no disco através de chamadas a essas ferramentas, a menos que sejam explicitamente conectadas ao CrewAI.

---

## 4. Classificação Rigorosa de Riscos Operacionais Críticos

### 🚨 Risco Crítico 1: `tools/git.py` — Destruição Potencial de Arquivos Não Rastreados
* **Comandos Executados:** `git reset --hard` e `git clean -fd` ([Linhas 97 e 99](file:///home/devan/Documentos/Jinsai-G15/tools/git.py#L97-L99)).
* **Análise de Segurança:**
  * **Confirmação Prévia:** **NÃO**. O rollback executa imediatamente se invocado.
  * **Preservação de Mudanças Não Rastreadas Anteriores:** **NÃO**. O `git clean -fd` remove *quaisquer* arquivos e pastas não rastreados no repositório inteiro, inclusive arquivos criados manualmente pelo desenvolvedor antes da execução do agente!
  * **Isolamento de Escopo:** O comando é executado na raiz do repositório Git, sem filtro por subpasta.
* **Classificação:** **RISCO CRÍTICO DE PERDA DE DADOS**. Requer implementação urgente de stash seguro ou restrição do clean aos arquivos da tarefa.

### 🚨 Risco Crítico 2: `tools/testing.py` — Falsa Sensação de Sandbox
* **Mecanismo Real:** Subprocesso local não confinado (`subprocess.run([pytest_cmd, ...], cwd=str(root))`).
* **Análise de Segurança:**
  * Não há isolamento via container (Docker/Podman), nem cgroups, nem chroot, nem usuário restrito.
  * O código de teste executado tem **acesso total** ao sistema de arquivos do usuário (`/home/devan/`), variáveis de ambiente de sessão, rede externa e processos locais.
* **Classificação:** **RISCO DE SEGURANÇA ALTO**. Testes com scripts maliciosos ou testes de integração mal configurados podem apagar dados reais do usuário fora da raiz do projeto.

### ⚠️ Risco 3: `run_crew.sh` — Instalação Automática e Reprodutibilidade Não Garantida
* **Mecanismo:** Criação de `venv` e execução de `pip install -r requirements.txt` se a pasta `venv/` não existir.
* **Análise de Reprodutibilidade:**
  * Não utiliza arquivo de lock estrito (`pip-tools` / `poetry.lock`).
  * Dependências secundárias de `crewai` e `chromadb` podem sofrer atualizações automáticas upstream, quebrando compatibilidade sem intervenção do usuário.
* **Classificação:** **RISCO DE ESTABILIDADE MÉDIO-ALTO**.

### ⚠️ Risco 4: `core/rag_engine.py` — Degradação Silenciosa por Falta de ChromaDB
* **Mecanismo:** Bloco `try/except ImportError` em `_init_chromadb()` ([Linha 95](file:///home/devan/Documentos/Jinsai-G15/core/rag_engine.py#L95)).
* **Análise Comportamental:**
  * Se `chromadb` não estiver instalado, `self._collection` torna-se `None`.
  * `index_project()` retorna `{'indexed': 0, 'skipped': 0}` sem levantar erro.
  * `format_context_for_llm()` retorna texto genérico *"Nenhum trecho de código indexado relevante encontrado."*
* **Classificação:** **RISCO DE QUALIDADE OCULTA**. O agente executa com contexto severamente reduzido sem alertar explicitamente o usuário no terminal.

---

## 5. Hipóteses de Runtime a Validar (Distinção de Fatos vs Hipóteses)

| Item | Afirmação | Status Epistemológico | Fatores de Dependência |
| :--- | :--- | :--- | :--- |
| **VRAM na RTX 3050** | *"Qwen 2.5 Coder 3B cabe 100% na VRAM"* | **Fato Confirmado** em quantização Q4_K_M com contexto ≤ 4096 tokens (~2.2GB). | Driver NVIDIA 610.57 + CUDA 13.3. |
| **VRAM sob Carga MoE** | *"DeepSeek-Coder-V2 Lite 16B força offload ou OOM"* | **Hipótese de Runtime** | Depende do `num_gpu_layers` alocado pelo Ollama e da concorrência de processos Wayland/KWin na GPU. |
| **Timeouts de Nuvem** | *"Claude 3.7 Sonnet com Thinking excede timeouts"* | **Hipótese de Runtime** | Depende da latência de rede e do `thinking_budget` configurado no LiteLLM/CrewAI. |
| **Busca com Ripgrep** | *"search_code usa rg com máxima velocidade"* | **Hipótese de Ambiente** | Depende da presença do binário `rg` no PATH do sistema operacional. |

---

## 6. Mapeamento Módulo a Módulo com Confiança Multidimensional

### 6.1. `core/vram_manager.py`
* **Responsabilidade:** Monitorar VRAM da RTX 3050 e descarregar modelos no Ollama via `/api/generate` (`keep_alive: 0`).
* **Exportações:** `VRAMManager` (`get_gpu_vram_status`, `get_running_ollama_models`, `unload_model`, `unload_all`, `warm_up_model`, `scoped_model`).
* **Consumidores Reais:** `run_developer_crew.py:123, 272` (apenas `get_gpu_vram_status` e `get_running_ollama_models`).
* **Matriz de Confiança:**
  * Estrutural: **ALTA** | Comportamental: **BAIXA** | Runtime: **MÉDIA** | Contratual: **MÉDIA**
* **Lacunas:** `unload_all` e `scoped_model` não são chamados no pipeline e não possuem testes com mocks de rede.

### 6.2. `core/state_machine.py`
* **Responsabilidade:** FSM formal do ciclo autônomo e contenção de loops infinitos de reparo.
* **Exportações:** `DevelopmentState`, `DevelopmentStateMachine`.
* **Consumidores Reais:** `run_developer_crew.py:96, 173, 206, 229, 235, 238, 240`, `tests/test_base.py:133-152`.
* **Matriz de Confiança:**
  * Estrutural: **ALTA** | Comportamental: **ALTA** | Runtime: **ALTA** | Contratual: **ALTA**
* **Métricas de Teste:** 1 teste unitário dedicado (`test_state_machine_transitions`), 7 asserções cobrindo transições válidas e bloqueio ao estourar `max_repair_attempts`.

### 6.3. `core/router.py`
* **Responsabilidade:** Triagem heurística/determinística baseada em regex e contagem de palavras.
* **Exportações:** `RoutingDecision`, `TaskRouter`.
* **Consumidores Reais:** `tests/test_base.py:53-70`. (**Ocioso em `run_developer_crew.py`**).
* **Matriz de Confiança:**
  * Estrutural: **ALTA** | Comportamental: **ALTA** | Runtime: **ALTA** | Contratual: **BAIXA** (desconectado do orquestrador).

### 6.4. `core/rag_engine.py`
* **Responsabilidade:** Chunking de código por linhas, hash SHA-256 e indexação vetorial no ChromaDB via `nomic-embed-text`.
* **Exportações:** `calculate_sha256`, `CodeChunk`, `LocalCodeRAG`.
* **Consumidores Reais:** `run_developer_crew.py:155-157`.
* **Matriz de Confiança:**
  * Estrutural: **ALTA** | Comportamental: **BAIXA** | Runtime: **BAIXA** | Contratual: **MÉDIA**
* **Lacunas:** Nenhum teste unitário exercitando `index_project()` ou `query_relevant_chunks()`.

### 6.5. `core/errors.py`
* **Responsabilidade:** Exceções formais e validadores rápidos de ambiente (`fail-fast`).
* **Exportações:** Exceções (`JinsaiError`, `SecurityViolationError`, etc.); funções de validação.
* **Consumidores Reais:** `run_developer_crew.py:113, 117, 132`, `tools/security.py:73, 79`, `tests/test_base.py:83, 94`.
* **Matriz de Confiança:**
  * Estrutural: **ALTA** | Comportamental: **MÉDIA** | Runtime: **MÉDIA** | Contratual: **ALTA**

### 6.6. `tools/security.py`
* **Responsabilidade:** Proteção contra Path Traversal, arquivos sensíveis e comandos destrutivos.
* **Exportações:** `BLOCKED_PATTERNS`, `BLOCKED_SHELL_PATTERNS`, `validate_safe_path`, `is_path_blocked`, `is_command_safe`.
* **Consumidores Reais:** Todos os módulos de `tools/*`, `tests/test_base.py:73-102`.
* **Matriz de Confiança:**
  * Estrutural: **ALTA** | Comportamental: **ALTA** | Runtime: **ALTA** | Contratual: **ALTA**
* **Métricas de Teste:** 1 teste unitário dedicado, 9 asserções cobrindo escapes de caminho (`../../`), segredos (`.env`, `id_rsa`) e comandos (`rm -rf /`).

### 6.7. `tools/filesystem.py`
* **Responsabilidade:** Inspeção da árvore de arquivos e leitura controlada de configurações.
* **Exportações:** `list_project_tree`, `read_file`, `get_file_metadata`, `read_project_config`.
* **Consumidores Reais:** `run_developer_crew.py:141, 142` (apenas `list_project_tree` e `read_project_config`).
* **Matriz de Confiança:**
  * Estrutural: **ALTA** | Comportamental: **BAIXA** | Runtime: **MÉDIA** | Contratual: **MÉDIA**
* **Lacunas:** `read_file` e `get_file_metadata` desconectados do orquestrador e sem testes unitários.

### 6.8. `tools/search.py`
* **Responsabilidade:** Busca textual de símbolos via `ripgrep` ou fallback Python.
* **Exportações:** `search_code`.
* **Consumidores Reais:** Nenhum consumidor ativo no código principal.
* **Matriz de Confiança:**
  * Estrutural: **ALTA** | Comportamental: **BAIXA** | Runtime: **BAIXA** | Contratual: **BAIXA**

### 6.9. `tools/patching.py`
* **Responsabilidade:** Mutação atômica e cirúrgica de arquivos.
* **Exportações:** `create_file`, `replace_range`, `apply_patch`, `delete_file`.
* **Consumidores Reais:** `tests/test_base.py:105-126`. (**Desconectado de `run_developer_crew.py`**).
* **Matriz de Confiança:**
  * Estrutural: **ALTA** | Comportamental: **ALTA** | Runtime: **ALTA** | Contratual: **BAIXA** (não conectado ao agente).

### 6.10. `tools/git.py`
* **Responsabilidade:** Checkpoints Git/snapshot e rollback de segurança.
* **Exportações:** `create_checkpoint`, `get_git_diff`, `get_git_status`, `rollback_checkpoint`.
* **Consumidores Reais:** `run_developer_crew.py:161` (apenas `create_checkpoint`).
* **Matriz de Confiança:**
  * Estrutural: **ALTA** | Comportamental: **BAIXA** | Runtime: **BAIXA** | Contratual: **BAIXA**
* **Lacunas:** Rollback nunca é acionado no orquestrador; sem testes automatizados com git mock.

### 6.11. `tools/testing.py`
* **Responsabilidade:** Execução de testes unitários (`pytest`) e sintaxe (`py_compile`).
* **Exportações:** `run_unit_tests`, `run_syntax_check`.
* **Consumidores Reais:** `run_developer_crew.py:232` (apenas `run_unit_tests`).
* **Matriz de Confiança:**
  * Estrutural: **ALTA** | Comportamental: **BAIXA** | Runtime: **MÉDIA** | Contratual: **BAIXA**

### 6.12. `memory/project_memory.py`
* **Responsabilidade:** Persistência em `.jinsai/` de decisões (`decisions.md`), tarefas e logs.
* **Exportações:** `ProjectMemory`.
* **Consumidores Reais:** `run_developer_crew.py:147, 148, 244, 250`, `tests/test_base.py:154-175`.
* **Matriz de Confiança:**
  * Estrutural: **ALTA** | Comportamental: **ALTA** | Runtime: **ALTA** | Contratual: **MÉDIA**
* **Lacunas:** Métodos `save_plan` e `update_task_state` não são chamados pelo orquestrador no ciclo principal.

### 6.13. `run_developer_crew.py`
* **Responsabilidade:** Orquestrador central e interface CLI do agente.
* **Exportações:** `load_yaml`, `build_crewai_llm`, `execute_autonomous_cycle`, `main`.
* **Consumidores Reais:** `run_crew.sh`, desenvolvedor via terminal.
* **Matriz de Confiança:**
  * Estrutural: **ALTA** | Comportamental: **MÉDIA** | Runtime: **BAIXA** | Contratual: **BAIXA**

---

## 7. Contratos Externos e Contratos de Dados

### 7.1. Contratos de Integrações Externas

| Integração | Formato de Entrada | Formato de Saída | Falhas Mapeadas | Timeout | Retry | Fallback |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Ollama `/api/ps`** | N/A (GET) | JSON `{'models': [...]}` | `httpx.RequestError` | 5.0s | 0 | Retorna `[]` vazio |
| **Ollama `/api/generate`** | JSON `{'model': str, 'keep_alive': int}` | JSON `{'done': bool}` | `httpx.RequestError` | 10.0s | 0 | Log de erro; não trava |
| **Ollama `/api/embeddings`** | JSON `{'model': str, 'prompt': str}` | JSON `{'embedding': [float]}` | Timeout, modelo ausente | 30.0s | 0 | Retorna `[]` vazio |
| **Provedores de Nuvem (CrewAI)** | Prompts em Markdown | Textos gerados | Chave ausente, limite de cota | Padrão CrewAI | 2 (CrewAI) | Falha no `kickoff()` |
| **Subprocesso `pytest`** | Argumentos de linha de comando | `stdout`, `stderr`, código de retorno | `TimeoutExpired`, erro de sintaxe | 25.0s - 30.0s | 0 | Retorna `passed: False` |
| **Subprocesso `git`** | Argumentos de linha de comando | `stdout`, `stderr`, código de retorno | Repositório não Git, erro de lock | 15.0s | 0 | Fallback para snapshot local |

### 7.2. Contratos de Dados Persistentes (Schemas Locais)

#### A. `.jinsai/task_state.json`
```json
{
  "tasks": {
    "TASK-ID": {
      "status": "PENDING | IN_PROGRESS | TESTING | COMPLETED | BLOCKED",
      "created_at": "ISO-8601 Timestamp",
      "updated_at": "ISO-8601 Timestamp",
      "details": {
        "files": ["caminhos/dos/arquivos.py"]
      }
    }
  }
}
```

#### B. `.jinsai/execution_log.jsonl`
```jsonl
{"timestamp": "2026-09-09T19:40:00Z", "action": "TASK_COMPLETED", "metadata": {"prompt": "...", "preset": "economy"}}
```

#### C. `.jinsai_cache.json` (Cache de Hashes do RAG)
```json
{
  "caminho/relativo/arquivo.py": "hash_sha256_hexadecimal_64_chars"
}
```

---

## 8. Matriz de Impacto para Refatorações Futuras

Antes de alterar qualquer símbolo listado abaixo, consulte esta matriz e execute os testes correspondentes:

| Símbolo a Alterar | Módulo de Origem | Consumidores Diretos Afetados | Nível de Risco | Testes Obrigatórios Pós-Alteração |
| :--- | :--- | :--- | :--- | :--- |
| `validate_safe_path` | `tools/security.py` | `tools/filesystem.py`, `tools/patching.py`, `tools/testing.py` | 🔴 **CRÍTICO** | `pytest tests/test_base.py -k test_security_guardrails` |
| `is_path_blocked` | `tools/security.py` | `tools/security.py`, `tools/search.py` | 🔴 **CRÍTICO** | `pytest tests/test_base.py -k test_security_guardrails` |
| `DevelopmentStateMachine.transition_to` | `core/state_machine.py` | `run_developer_crew.py` | 🟡 **ALTO** | `pytest tests/test_base.py -k test_state_machine_transitions` |
| `LocalCodeRAG._chunk_file` | `core/rag_engine.py` | `LocalCodeRAG.index_project`, `run_developer_crew.py` | 🟡 **ALTO** | Criar teste mock para RAG antes de alterar |
| `create_checkpoint` | `tools/git.py` | `run_developer_crew.py:161` | 🔴 **CRÍTICO** | Validar retenção de commit em repositório Git de teste |
| `rollback_checkpoint` | `tools/git.py` | `run_developer_crew.py` (deve ser conectado) | 🔴 **CRÍTICO** | Testar se `git clean -fd` apaga arquivos fora da tarefa |
| `ProjectMemory.record_decision` | `memory/project_memory.py` | `run_developer_crew.py:244` | 🟢 **MÉDIO** | `pytest tests/test_base.py -k test_project_memory` |
| `VRAMManager.get_gpu_vram_status` | `core/vram_manager.py` | `run_developer_crew.py:123, 272` | 🟡 **ALTO** | Testar com `nvidia-smi` presente e ausente |

---

## 9. Mapeamento de Arquivos de Infraestrutura

* [`requirements.txt`](file:///home/devan/Documentos/Jinsai-G15/requirements.txt): Versões pinadas (`crewai==0.102.0`, `chromadb==0.5.23`, `httpx==0.28.1`, `pytest==8.3.4`).
* [`run_crew.sh`](file:///home/devan/Documentos/Jinsai-G15/run_crew.sh): Script mestre de bootstrap. Cria ambiente virtual, checa GPU e valida Ollama.
* [`.env.example`](file:///home/devan/Documentos/Jinsai-G15/.env.example): Declaração das variáveis `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, `OLLAMA_BASE_URL` e `JINSAI_DEFAULT_PROFILE`.
* [`.gitignore`](file:///home/devan/Documentos/Jinsai-G15/.gitignore): Exclusão de `venv/`, `.env`, `.jinsai_cache.json`, `.jinsai_chroma/`, `__pycache__/`.

---

## 10. Protocolo Obrigatório de Validação Pré-Refatoração

Qualquer agente ou desenvolvedor que for refatorar código no Jinsai-G15 deve seguir estritamente este protocolo:
1. **Consultar o Call Graph (Seção 2)** para identificar onde o símbolo é chamado.
2. **Verificar os Dead Imports e Desconexões (Seção 3)** para não assumir falsamente que uma ferramenta está sendo invocada pelo agente.
3. **Buscar Referências no Código:** Rodar grep estático no projeto (`grep_search` ou `rg`) para confirmar que não existem chamadas dinâmicas (`getattr`, etc.).
4. **Consultar a Matriz de Impacto (Seção 8)** para avaliar riscos colaterais.
5. **Executar a Bateria de Testes:** `pytest tests/ -v`.
6. **Não prosseguir se houver quebra de contratos de segurança.**
