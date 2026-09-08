# Plano de Atualização: Jinsai-G15 v2.2 (Dell G15 5520)

Este documento registra a especificação completa e o planejamento arquitetural da versão 2.2 do **Jinsai-G15**, calibrado para o hardware do **Dell G15 5520**:

* **Processador:** 12th Gen Intel Core i5-12500H (12 cores / 16 threads)
* **Memória RAM:** 16GB DDR
* **Placa de Vídeo:** NVIDIA GeForce RTX 3050 Mobile (4096 MiB VRAM GDDR6, CUDA 13.x)
* **Sistema Operacional:** BigLinux (Kernel 6.18, Arch/Manjaro based, KDE Plasma 6 Wayland)

---

## 1. Decisões Arquiteturais e Guardrails de VRAM

| Componente | Especificação Técnica | Justificativa de Hardware |
| :--- | :--- | :--- |
| **VRAM Guardrail** | Teto operacional de **3600 MiB / 4096 MiB**. | Evita OOM na RTX 3050 e paginação lenta para a RAM do sistema. |
| **Modelo Local de Código** | `qwen2.5-coder:3b` (Q4_K_M). | Consome ~2.2 GB de VRAM com contexto de 4096 tokens, rodando 100% via CUDA com alta taxa de geração de tokens (~70-90 tok/s). |
| **Manager de Nuvem** | Claude 3.7 Sonnet (Thinking Mode) / Gemini 2.0 Flash / DeepSeek R1 API. | Planejamento arquitetural de alto nível e síntese sem sobrecarregar a GPU local. |
| **RAG Incremental** | ChromaDB em RAM + Cache SHA-256 (`.jinsai_cache.json`). | Aproveita os 16 threads do i5-12500H para hashing e chunking, re-indexando apenas arquivos alterados. |
| **Lifecycle Manager** | `core/vram_manager.py` com `keep_alive: 5m` e descarga síncrona. | Mantém o modelo aquecido durante sessões ativas e libera VRAM quando necessário. |

---

## 2. Perfis Operacionais (Presets)

* **`offline`:** DeepSeek-R1 1.5B (raciocínio local) + Qwen 2.5 Coder 3B (código local) + nomic-embed-text (100% offline, zero custos).
* **`economy`:** Gemini 2.0 Flash (contexto de 1M tokens na nuvem) + Qwen 2.5 Coder 3B local na RTX 3050.
* **`precision`:** Claude 3.7 Sonnet (Extended Thinking Mode) + Qwen 2.5 Coder 3B ou Phi-3.5 local.
* **`deepseek_cloud`:** DeepSeek-Reasoner (R1 API na nuvem) + Qwen 2.5 Coder 3B local.
* **`moe_hybrid`:** DeepSeek-Coder-V2 Lite (16B MoE com 2.4B ativos) distribuído entre a RTX 3050 e os 16GB de RAM.
