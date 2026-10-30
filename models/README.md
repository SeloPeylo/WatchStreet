# Models

Put GGUF model files here; they are mounted read-only into the llama.cpp container (`/models`).
The files themselves are git-ignored.

```bash
./scripts/download_model.sh https://huggingface.co/<org>/<repo>/resolve/main/<file>.gguf
echo "LLAMA_MODEL=<file>.gguf" >> .env
echo "WATCHSTREET_AGENT_RUNNER=llama" >> .env
docker compose --profile llm-gpu up --build      # or --profile llm-cpu
```

Pick an **instruct model with tool-calling support** (e.g. Qwen2.5/Qwen3-Instruct, Llama 3.1/3.3
Instruct, Mistral-Instruct) – the harness uses tool calls. Without tool support the harness
falls back to a JSON answer automatically, with lower reliability.

Tuning in `.env`: `LLAMA_CTX` (context), `LLAMA_N_GPU_LAYERS` (0 = CPU only, 99 = all on GPU),
`LLAMA_THREADS`, `LLAMA_GPU_COUNT`, `LLAMA_MEM_LIMIT`, `LLAMA_PARALLEL`.
