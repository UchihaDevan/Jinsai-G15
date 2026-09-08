# Jinsai-G15 v2.2 (Dell G15 5520 Edition)

Sistema de **Agente Hierárquico Híbrido Local-First** calibrado especificamente para o hardware do **Dell G15 5520**:
* **CPU:** 12th Gen Intel Core i5-12500H (12 cores / 16 threads)
* **RAM:** 16GB DDR
* **GPU Dedicada:** NVIDIA GeForce RTX 3050 Mobile (4096 MiB VRAM GDDR6, CUDA 13.x)
* **SO:** BigLinux (Arch/Manjaro based, KDE Plasma 6 Wayland)

---

## 🚀 Como Executar

### 1. Pré-requisitos
Certifique-se de que o daemon do Ollama está rodando no sistema:
```bash
ollama serve
# Ou se estiver rodando como serviço do sistema:
systemctl status ollama
```

Para usar os modelos locais recomendados na RTX 3050, baixe-os uma única vez:
```bash
ollama pull qwen2.5-coder:3b
ollama pull nomic-embed-text
# Opcional para modo 100% offline:
ollama pull deepseek-r1:1.5b
```

### 2. Configurar Chaves de Nuvem (Opcional)
Se for utilizar perfis híbridos com nuvem (Claude 3.7 Sonnet ou Gemini 2.0 Flash), configure suas chaves no `.env`:
```bash
cp .env.example .env
nano .env
```

### 3. Modos de Uso

#### Modo Interativo
```bash
./run_crew.sh
```

#### Ver Telemetria de Hardware (VRAM da RTX 3050 & Modelos Ativos)
```bash
./run_crew.sh --status
```

#### Executar com Perfil Específico
```bash
# Perfil 100% Offline (Zero chamadas externas, sem custos de API)
./run_crew.sh --profile offline --prompt "Crie uma classe Python para cálculo de juros compostos com testes unitários"

# Perfil Economia (Gemini 2.0 Flash + Qwen 2.5 Coder 3B local)
./run_crew.sh --profile economy --prompt "Refatore o módulo de autenticação"

# Perfil Alta Precisão (Claude 3.7 Sonnet com Thinking Mode + Qwen 2.5 Coder local)
./run_crew.sh --profile precision --prompt "Desenhe a arquitetura de um pipeline assíncrono de eventos"
```

#### Executar com RAG Local no seu Projeto
Para que os agentes leiam apenas os arquivos relevantes do seu projeto usando o ChromaDB e embeddings sem estourar o limite de tokens:
```bash
./run_crew.sh --project /caminho/do/seu/projeto --prompt "Onde está implementada a função de hash de senhas e como posso torná-la mais segura?"
```

---

## 📂 Estrutura de Arquivos

```
/home/devan/Documentos/Jinsai-G15/
├── config/
│   ├── presets.yaml        # Configuração dos perfis e modelos (locais e nuvem)
│   ├── agents.yaml         # Papéis e backstories do Arquiteto e Desenvolvedor
│   └── tasks.yaml          # Definições modulares das tarefas do CrewAI
├── core/
│   ├── vram_manager.py     # Monitor de VRAM (RTX 3050 4GB) e ciclo de vida do Ollama
│   ├── router.py           # Roteador dual-stage determinístico + escopo
│   └── rag_engine.py       # RAG local incremental com hash SHA-256 e ChromaDB
├── run_developer_crew.py   # Script mestre em Python integrado com CrewAI
├── run_crew.sh             # Script inicializador com verificações de GPU e ambiente
├── requirements.txt        # Dependências do Python
└── .env.example            # Modelo de configuração de variáveis
```

---

## 🛡️ Gestão de VRAM na RTX 3050 (4096 MiB)
* O `qwen2.5-coder:3b` consome aproximadamente **2.2 GB de VRAM** em quantização Q4 com KV Cache de 4096 tokens, rodando **100% dentro da RTX 3050** com velocidade média de **~70 a 90 tokens/s via CUDA**.
* O `vram_manager.py` garante que o modelo de embedding (`nomic-embed-text`, ~274MB) e o modelo de código nunca concorram por VRAM além do limite de segurança (3600 MiB), acionando `keep_alive: 0` quando necessário.
