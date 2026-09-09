# Nova análise técnica do Jinsai-G15

## Escopo e estado analisado

Esta análise foi feita sobre o branch `main` disponível em 9 de setembro de 2026. O repositório agora contém os commits `5d1c211` — commit inicial —, `c19f0fa` — versão 3.0 — e `1934d40` — mapa do projeto. Em comparação com a análise anterior, houve uma evolução importante: o projeto passou a incluir memória de projeto, ferramentas de filesystem, patching, busca, Git, testes, segurança e uma máquina de estados.

Também executei a compilação sintática do repositório. O comando `python3 -m compileall -q .` passou. A suíte não foi executada porque o ambiente da auditoria não possui o comando `pytest`; portanto, os testes declarados no repositório ainda não foram validados em runtime nesta análise.

## Veredito executivo

O Jinsai-G15 **deixou de ser apenas um pipeline textual de planejamento e geração**. Ele agora tem boa parte dos blocos necessários para um agente de desenvolvimento assistido:

- discovery da árvore do projeto;
- leitura de arquivos de configuração;
- RAG incremental;
- memória persistente de decisões;
- máquina de estados;
- checkpoints Git;
- ferramentas de criação e alteração de arquivos;
- busca textual;
- executor de testes;
- controles básicos contra path traversal e acesso a segredos.

Entretanto, ele **ainda não é um agente autônomo de desenvolvimento funcional**. O problema central é arquitetural: as ferramentas de leitura detalhada, busca e alteração de arquivos existem, mas não são anexadas aos agentes CrewAI. O `dev_agent` continua sem `tools=[...]`, portanto continua gerando código em texto. O orquestrador também não salva o plano, não atualiza estados de tarefas, não chama rollback quando os testes falham e não possui loop de reparo real.

A classificação atual é:

> **Protótipo avançado de agente assistido, aproximadamente Nível 1,5 de autonomia.**
>
> Ele consegue descobrir contexto, executar um planejamento textual, criar checkpoint e rodar testes após a execução. Ainda não consegue implementar de forma autônoma porque o resultado da implementação não é aplicado ao projeto pelo agente.

## Comparação com a análise anterior

| Área | Antes | Estado atual | Avaliação |
|---|---|---|---|
| Importação principal | Import quebrado para `core.memory_manager` | Corrigido para `core.vram_manager` | Melhoria confirmada |
| Estrutura do projeto | Apenas RAG sem árvore | `list_project_tree` e leitura de configurações | Implementado, mas limitado |
| Leitura direta | Inexistente | `read_file` existe | Ainda não conectado ao agente |
| Busca de código | Inexistente | `search_code` existe | Ainda não conectado ao agente |
| Escrita/patch | Inexistente | `create_file`, `replace_range`, `apply_patch`, `delete_file` | Ainda não conectado ao agente |
| Memória | Apenas cache/RAG | `.jinsai/decisions.md`, `plan.yaml`, estados e logs | Parcialmente integrada |
| Máquina de estados | Inexistente | Implementada | Apenas parcialmente respeitada pelo fluxo |
| Testes | Não executados pelo pipeline | `run_unit_tests` é chamado após o Crew | Não há correção automática após falhas |
| Rollback | Não havia | Função implementada | Importada, mas nunca chamada |
| Skills/tools | Ausentes | Funções de ferramentas existem | Não estão registradas em `Agent(tools=...)` |

## 1. O que o projeto consegue fazer atualmente

### Discovery

Quando `--project` é informado, o orquestrador valida a pasta, gera uma árvore com profundidade máxima 3 e até 100 entradas, lê arquivos de configuração conhecidos e recupera decisões anteriores da pasta `.jinsai/`. Isso melhora significativamente o contexto inicial do agente.

### RAG

O `LocalCodeRAG` continua indexando arquivos suportados com ChromaDB e embeddings do Ollama. Ele é utilizado como camada complementar ao contexto estrutural. A recuperação continua limitada a quatro chunks e ainda existe degradação silenciosa se ChromaDB ou o serviço de embeddings falhar.

### Planejamento

O agente gerente continua gerando uma especificação textual em Markdown. O plano ainda não é convertido automaticamente em um objeto estruturado nem salvo por `ProjectMemory.save_plan()`.

### Implementação

A tarefa de implementação é executada por um agente CrewAI, mas o agente recebe apenas a descrição do plano e o contexto textual. Como nenhuma ferramenta é anexada, ele não pode chamar `create_file`, `read_file`, `search_code` ou `apply_patch`. O resultado continua sendo uma resposta textual retornada por `crew.kickoff()`.

### Testes

Depois do `kickoff()`, o orquestrador executa `run_unit_tests()` se existir um diretório `tests/` no projeto. Isso é uma melhoria real, mas o executor usa `subprocess.run()` localmente e não em sandbox. Além disso, o resultado dos testes não é usado para iniciar uma nova tentativa de implementação.

## 2. Problemas críticos do fluxo principal

### 2.1 As tools não estão conectadas aos agentes

O problema mais importante permanece. Em `run_developer_crew.py`, os agentes são criados aproximadamente assim:

```python
manager_agent = Agent(..., llm=manager_llm, verbose=True)
dev_agent = Agent(..., llm=dev_llm, verbose=True)
```

Não existe:

```python
tools=[...]
```

Consequentemente, estas funções estão disponíveis apenas como funções Python internas, não como capacidades que o LLM pode chamar:

- `read_file`;
- `get_file_metadata`;
- `search_code`;
- `create_file`;
- `replace_range`;
- `apply_patch`;
- `delete_file`;
- funções Git;
- ferramentas de validação.

Esse fato impede chamar o sistema de agente autônomo. A implementação deve ser conectada por wrappers compatíveis com o CrewAI, com schemas de argumentos, descrição, limites de uso e registro de auditoria.

### 2.2 O plano persistente foi implementado, mas não utilizado

`ProjectMemory` possui:

- `save_plan()`;
- `load_plan()`;
- `update_task_state()`;
- `get_task_states()`;
- `record_decision()`;
- `append_log()`.

O orquestrador utiliza apenas `read_decisions()`, `record_decision()` e `append_log()`. Ele nunca chama `save_plan()` nem `update_task_state()`. Portanto, `.jinsai/plan.yaml` e o rastreamento de tarefas não representam o fluxo real.

Além disso, o registro final afirma genericamente:

```text
Implementação realizada e validada pelo pipeline autônomo
```

mesmo quando não houve escrita de arquivos e mesmo quando os testes falharam. Isso produz memória falsa e precisa ser corrigido.

### 2.3 O loop de reparo não existe

A máquina de estados possui `REPAIRING` e limita tentativas. Porém, o fluxo principal faz apenas:

```text
TESTING → REPAIRING
```

quando o teste falha. Depois disso, ele não:

- envia o erro ao agente;
- pede uma correção;
- aplica um patch;
- executa os testes novamente;
- verifica o limite de tentativas;
- faz rollback;
- marca a tarefa como bloqueada.

Na prática, `REPAIRING` é apenas um estado registrado, não uma etapa executável.

### 2.4 O estado final pode ser incorreto

Se os testes falharem, o estado passa a `REPAIRING`. Mesmo assim, o orquestrador continua registrando a execução como concluída e retorna o resultado original. Ele não transiciona para `BLOCKED`, não retorna erro estruturado e não comunica que a implementação não foi validada.

Se não houver diretório `tests/`, o código pula a validação e transiciona diretamente para `COMPLETED`. Isso permite que uma tarefa seja considerada concluída sem qualquer teste, sintaxe ou revisão de diff.

### 2.5 `REVIEWING` nunca é utilizado

A máquina de estados declara `REVIEWING`, mas `run_developer_crew.py` não faz essa transição. Também não há revisor independente, análise de diff, verificação de critérios de aceite ou checagem de arquivos alterados.

### 2.6 O checkpoint pode comprometer alterações prévias do usuário

`create_checkpoint()` detecta arquivos modificados e executa:

```bash
git add -A
git commit -m "[jinsai-checkpoint] ..."
```

Isso cria um commit automático contendo mudanças que podem ter sido feitas pelo usuário antes de iniciar o Jinsai. O agente não pede confirmação, não registra exatamente quais arquivos pertenciam ao usuário e não cria uma branch isolada.

Esse comportamento é inadequado para um sistema autônomo. O correto seria:

1. detectar alterações prévias;
2. recusá-las ou criar um snapshot reversível separado;
3. trabalhar em uma branch própria;
4. nunca fazer commit de alterações prévias sem autorização explícita.

### 2.7 O rollback é perigoso e está desconectado

`rollback_checkpoint()` executa:

```bash
git reset --hard <commit>
git clean -fd
```

Além de não ser chamado atualmente, esse mecanismo poderia apagar arquivos não rastreados do projeto inteiro, incluindo arquivos criados manualmente pelo usuário antes da execução. Ele não restringe a limpeza aos arquivos criados pela tarefa.

Esse risco precisa ser resolvido antes de conectar o rollback ao loop autônomo.

## 3. Qualidade das ferramentas novas

### Filesystem

`list_project_tree()` e `read_file()` são boas adições. A leitura limita tamanho e permite intervalos de linhas. `validate_safe_path()` impede escapar da raiz e bloqueia padrões de segredos.

Limitações:

- a árvore oculta todos os diretórios iniciados por ponto, incluindo eventualmente configurações relevantes;
- `list_project_tree()` não informa truncamento de diretórios, apenas o limite geral de entradas;
- `read_file()` ainda não tem testes próprios;
- arquivos binários e codificações especiais não são tratados explicitamente;
- não há limite de chamadas por tarefa;
- a tool não está exposta ao agente.

### Patching

`apply_patch()` exige que o trecho-alvo apareça exatamente uma vez, o que é uma proteção útil. Porém, as escritas não são atômicas: o código escreve diretamente no arquivo. Uma falha durante a escrita pode deixar o arquivo parcialmente gravado.

Também falta:

- criação de backup por arquivo;
- validação de hash antes da alteração;
- verificação de que o arquivo não mudou desde a leitura;
- diff obrigatório antes da aplicação;
- limite global de arquivos e linhas modificadas.

Há ainda um erro menor em `create_file()`: depois de escrever, a função verifica `safe_path.exists()` para decidir se a ação foi `created` ou `overwritten`. Como o arquivo já existe nesse momento, um arquivo recém-criado pode ser reportado como `overwritten`.

### Busca

`search_code()` usando `ripgrep` é útil, mas ainda é uma função isolada. O fallback Python ignora diretórios ocultos e alguns diretórios, mas os filtros não são idênticos aos do caminho com `rg`. Isso pode gerar resultados diferentes conforme o ambiente.

### Testes

`run_unit_tests()` executa código do projeto no mesmo ambiente do usuário. Não existe container, usuário restrito, cgroup ou isolamento de rede. A função importa `is_command_safe`, mas não chama essa validação antes de executar o comando.

O teste do projeto precisa ser tratado como execução potencialmente hostil, especialmente quando o agente também pode modificar os arquivos.

### Git

O checkpoint e o diff fornecem uma boa base, mas o design atual assume que qualquer repositório Git pode receber commits automáticos. Isso precisa ser substituído por branch de tarefa ou snapshot controlado.

## 4. Memória atual

A memória de projeto agora existe de forma concreta em `.jinsai/`:

```text
.jinsai/
├── decisions.md
├── plan.yaml
├── task_state.json
└── execution_log.jsonl
```

Isso é uma evolução importante em relação à análise anterior. A memória é persistente, legível e específica por projeto.

Contudo, ela ainda não é memória dinâmica completa porque:

- não existe memória conversacional do CrewAI;
- `memory=True` não é usado no `Crew`;
- o plano não é salvo pelo fluxo;
- os estados das tarefas não são atualizados;
- decisões são registradas depois da execução, não extraídas de forma confiável do plano e do resultado;
- o registro final pode afirmar sucesso sem validação real;
- não existe mecanismo de recuperação semântica das decisões, apenas leitura de um trecho final de até 2.000 caracteres.

A classificação correta é:

> **Memória persistente de projeto: implementada parcialmente. Memória dinâmica conversacional: não implementada. Memória semântica de decisões: não implementada.**

## 5. Planejamento atual

O sistema ainda possui planejamento de alto nível em Markdown. Para planejamento de projeto real, falta transformar o resultado em um contrato estruturado e validável.

O plano deveria ter pelo menos:

```yaml
project: ...
assumptions: []
constraints: []
tasks:
  - id: TASK-001
    description: ...
    files: []
    dependencies: []
    acceptance_criteria: []
    validation_commands: []
```

Depois, o sistema deveria:

1. salvar o plano;
2. validar o schema;
3. criar estados para cada tarefa;
4. escolher uma tarefa desbloqueada;
5. limitar a implementação aos arquivos planejados;
6. validar os critérios de aceite;
7. atualizar o estado;
8. seguir para a próxima tarefa.

Sem esse ciclo, o agente ainda planeja uma resposta, não um projeto executável de forma controlada.

## 6. Segurança: melhorias e riscos restantes

### Melhorias existentes

A versão atual inclui:

- prevenção contra path traversal;
- bloqueio de `.env`, chaves, certificados e credenciais;
- bloqueio de alguns comandos destrutivos;
- limite de tamanho na leitura;
- checkpoint antes da tarefa;
- limite de tentativas na máquina de estados.

### Riscos que ainda impedem autonomia segura

1. **Execução local de testes sem isolamento.** Um teste do projeto pode acessar arquivos fora da raiz, rede, ambiente e processos do usuário.
2. **Rollback destrutivo.** `git clean -fd` pode apagar arquivos não rastreados.
3. **Commit automático de alterações prévias.** O checkpoint pode incorporar trabalho do usuário.
4. **Validação frágil de shell.** Uma lista de substrings proibidos não é uma política de execução segura.
5. **Tools desconectadas.** As validações existem, mas o LLM ainda não é obrigado a usá-las.
6. **Ausência de autorização por operação.** Não há modo read-only, dry-run ou política para operações sensíveis.
7. **Ausência de limite de impacto.** Não há limite efetivo de número de arquivos, linhas alteradas ou tamanho do diff.
8. **Ausência de verificação de segredos em conteúdo.** O bloqueio atua principalmente por caminho; um segredo em outro arquivo ainda pode ser exposto.

## 7. Estado de prontidão por capacidade

| Capacidade | Estado atual | Pronto para uso autônomo? |
|---|---|---|
| Descobrir árvore do projeto | Implementado | Parcialmente |
| Ler arquivo específico | Implementado como função | Não, não conectado ao agente |
| Buscar símbolos | Implementado como função | Não, não conectado ao agente |
| Gerar plano | Implementado em texto | Não, falta persistência e validação estrutural |
| Criar/modificar arquivos | Implementado como função | Não, não conectado ao agente |
| Executar testes | Implementado | Não, sem sandbox e sem repair loop |
| Detectar falhas | Parcialmente | Sim, mas só registra estado |
| Corrigir falhas | Não implementado no fluxo | Não |
| Rollback | Implementado, mas perigoso e desconectado | Não |
| Memória de decisões | Implementada | Parcialmente |
| Memória conversacional | Não implementada | Não |
| Revisão de diff | Função importada, não usada | Não |
| Skills CrewAI | Não conectadas | Não |
| Controle de VRAM | Telemetria implementada | Não há coordenação real no fluxo |
| Testes automatizados do Jinsai | Declarados | Não verificados neste ambiente |

## 8. O que falta para se tornar um agente autônomo de verdade

A prioridade não deve ser adicionar mais modelos ou mais agentes. O gargalo atual é a integração operacional.

### Fase 1 — Tornar o ciclo realmente executável

1. Criar wrappers CrewAI para todas as tools seguras.
2. Anexar as tools aos agentes com `tools=[...]`.
3. Fazer o agente implementar via patch, não via blocos de código no stdout.
4. Salvar o plano em `.jinsai/plan.yaml`.
5. Atualizar `task_state.json` em cada transição.
6. Registrar cada tool call em `execution_log.jsonl`.

### Fase 2 — Implementar validação e reparo

1. Coletar diff depois da implementação.
2. Executar sintaxe, testes e lint conforme o projeto.
3. Enviar falhas ao agente de reparo.
4. Aplicar no máximo três correções.
5. Reexecutar a validação após cada correção.
6. Marcar como `COMPLETED` somente quando os critérios passarem.
7. Marcar como `BLOCKED` quando o limite for atingido.

### Fase 3 — Corrigir o modelo de segurança

1. Trabalhar em branch criada pelo Jinsai.
2. Nunca fazer commit automático de alterações prévias.
3. Substituir `git clean -fd` por rollback de arquivos pertencentes à tarefa.
4. Usar container ou sandbox para testes.
5. Implementar modo read-only e dry-run.
6. Exigir aprovação para excluir arquivos, alterar dependências, migrar banco ou executar comandos de rede.

### Fase 4 — Melhorar o planejamento

1. Usar schema estruturado para planos.
2. Dividir projetos em tarefas independentes.
3. Registrar dependências entre tarefas.
4. Associar cada tarefa a arquivos permitidos e critérios de aceite.
5. Retomar execuções interrompidas a partir de `task_state.json`.

### Fase 5 — Memória e qualidade

1. Ativar memória conversacional somente se houver uma política clara de escopo.
2. Indexar decisões e planos para recuperação semântica.
3. Expirar ou revisar memórias obsoletas.
4. Registrar evidências de cada decisão.
5. Criar testes de integração com Ollama, CrewAI, ChromaDB e filesystem.
6. Medir taxa de sucesso, arquivos alterados indevidamente, tentativas e tempo.

## Conclusão

A nova versão representa um avanço real e corrigiu a principal falha apontada anteriormente: o import quebrado e a ausência de infraestrutura operacional. O projeto agora tem componentes que se parecem com uma plataforma de agente de desenvolvimento.

A lacuna decisiva, porém, permanece: **as capacidades operacionais foram implementadas como módulos Python, mas não foram conectadas aos agentes nem ao ciclo de execução**. Por isso, o Jinsai ainda não transforma o plano em alterações reais de código.

O próximo marco correto é pequeno e verificável:

> **Conectar somente `list_project_tree`, `read_file`, `search_code`, `apply_patch`, `git_diff` e `run_syntax_check` ao agente, executar em uma branch temporária, salvar o plano, mostrar o diff e validar uma tarefa simples de ponta a ponta.**

Depois que esse fluxo funcionar, deve-se implementar o repair loop e a sandbox de testes. Só então o Jinsai estará próximo de um agente autônomo de desenvolvimento confiável.

## Referências

[1]: https://github.com/UchihaDevan/Jinsai-G15 "Repositório oficial do Jinsai-G15"
[2]: https://docs.crewai.com/v1.15.17/en/concepts/tools "CrewAI — Tools"
[3]: https://docs.crewai.com/v1.15.17/en/concepts/memory "CrewAI — Memory"

*Auditoria baseada no estado do branch `main` e nos commits disponíveis no momento da análise.*
