#!/usr/bin/env bash
# ==============================================================================
# Jinsai-G15 v2.2 - Script Orquestrador Mestre
# Hardware: Dell G15 5520 (Intel i5-12500H, 16GB RAM, RTX 3050 4GB VRAM)
# SO: BigLinux / Arch Linux (CUDA 13.x)
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Cores para feedback visual no terminal
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=====================================================${NC}"
echo -e "${BLUE}      Jinsai-G15 v2.2 - Agente Hierárquico Local     ${NC}"
echo -e "${BLUE}=====================================================${NC}"

# 1. Validação de Hardware NVIDIA
if command -v nvidia-smi &> /dev/null; then
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -n 1)
    VRAM_INFO=$(nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits | head -n 1)
    echo -e "${GREEN}[OK] GPU Detectada:${NC} $GPU_NAME (VRAM: $VRAM_INFO MiB)"
else
    echo -e "${YELLOW}[AVISO] nvidia-smi não encontrado. Aceleração CUDA pode falhar.${NC}"
fi

# 2. Validação do Servidor Ollama
echo -e "${BLUE}[INFO] Verificando daemon do Ollama...${NC}"
if curl -s http://localhost:11434/api/tags &> /dev/null; then
    echo -e "${GREEN}[OK] Ollama ativo e respondendo em http://localhost:11434${NC}"
else
    echo -e "${RED}[ERRO] O serviço do Ollama não está rodando!${NC}"
    echo -e "Inicie o Ollama em outro terminal com: 'ollama serve' ou 'systemctl start ollama'"
    exit 1
fi

# 3. Gerenciamento do Ambiente Virtual Python
VENV_DIR="$SCRIPT_DIR/venv"
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}[INFO] Criando ambiente virtual Python (venv)...${NC}"
    python3 -m venv "$VENV_DIR"
    echo -e "${GREEN}[OK] Ambiente virtual criado em: $VENV_DIR${NC}"
    echo -e "${YELLOW}[INFO] Instalando dependências do requirements.txt...${NC}"
    "$VENV_DIR/bin/pip" install --upgrade pip
    "$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"
    echo -e "${GREEN}[OK] Dependências instaladas com sucesso!${NC}"
fi

# Ativação do ambiente virtual
source "$VENV_DIR/bin/activate"

# 4. Arquivo de Variáveis de Ambiente (.env)
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    if [ -f "$SCRIPT_DIR/.env.example" ]; then
        echo -e "${YELLOW}[INFO] Criando arquivo .env a partir de .env.example...${NC}"
        cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
        echo -e "${YELLOW}[AVISO] Lembre-se de configurar suas chaves no arquivo .env se for usar modelos em nuvem!${NC}"
    fi
fi

# 5. Execução do Script Python repassando os parâmetros
echo -e "${BLUE}[INFO] Executando Jinsai-G15...${NC}\n"
python3 "$SCRIPT_DIR/run_developer_crew.py" "$@"
