"""
Local inference server for Phi-3-mini-4k-instruct + LoRA adapter.

OpenAI-compatible /v1/chat/completions endpoint. The orchestrator
points base_url here when configured, zero code changes needed.

Usage:
    # install deps first:
    pip install torch transformers peft accelerate sentencepiece

    python -m app.ai.serving.server
    # or: uvicorn app.ai.serving.server:app --port 8001

Env vars:
    TAAZI_LORA_BASE_MODEL   (default: microsoft/Phi-3-mini-4k-instruct)
    TAAZI_LORA_ADAPTER_PATH (default: <app_dir>/taazi-adapter-final)
    TAAZI_LORA_PORT         (default: 8001)
    TAAZI_LORA_DEVICE       (default: auto — mps/cuda/cpu)
    TAAZI_LORA_MERGE        (default: true — fuse adapter into base model)
"""

import os
import time
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import torch
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("taazi.lora")

BASE_MODEL = os.getenv("TAAZI_LORA_BASE_MODEL", "microsoft/Phi-3-mini-4k-instruct")
_DEFAULT_ADAPTER = str(Path(__file__).parent / "taazi-adapter-final")
ADAPTER_PATH = os.getenv("TAAZI_LORA_ADAPTER_PATH", _DEFAULT_ADAPTER)
DEVICE = os.getenv("TAAZI_LORA_DEVICE", "auto")
_MERGE = os.getenv("TAAZI_LORA_MERGE", "true").lower() in ("1", "true", "yes")

model = None
tokenizer = None


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str = ""
    messages: list[ChatMessage]
    temperature: float = 0.3
    max_tokens: int = 512
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0


class ChatResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[dict]
    usage: dict


def _resolve_device() -> str:
    if DEVICE != "auto":
        return DEVICE
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global model, tokenizer
    import transformers
    from peft import PeftModel

    device = _resolve_device()
    logger.info("Loading base model %s on %s", BASE_MODEL, device)

    tokenizer = transformers.AutoTokenizer.from_pretrained(BASE_MODEL)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    torch_dtype = torch.float16 if device in ("cuda", "mps") else torch.float32
    model = transformers.AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch_dtype,
        device_map=device if device != "mps" else None,
    )
    if device == "mps":
        model = model.to(device)

    if os.path.isdir(ADAPTER_PATH):
        logger.info("Loading LoRA adapter from %s", ADAPTER_PATH)
        model = PeftModel.from_pretrained(model, ADAPTER_PATH)
        if _MERGE:
            logger.info("Fusing adapter into base model...")
            model = model.merge_and_unload()
    else:
        logger.warning("Adapter path %s not found — running base model only", ADAPTER_PATH)

    model.eval()
    logger.info("Model loaded on %s", device)
    yield


app = FastAPI(title="Taazi LoRA Inference Server", lifespan=lifespan)


_model_id = 0


@app.post("/v1/chat/completions")
async def chat_completion(req: ChatRequest):
    global _model_id
    start = time.monotonic()

    prompt = tokenizer.apply_chat_template(
        [m.model_dump() for m in req.messages],
        tokenize=False,
        add_generation_prompt=True,
    )

    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=req.max_tokens,
            temperature=req.temperature,
            top_p=req.top_p,
            do_sample=req.temperature > 0,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )

    generated = outputs[0][inputs.input_ids.shape[1]:]
    text = tokenizer.decode(generated, skip_special_tokens=True)
    elapsed_ms = (time.monotonic() - start) * 1000.0
    _model_id += 1

    return ChatResponse(
        id=f"chatcmpl-{_model_id}",
        created=int(time.time()),
        model=req.model or "phi-3-lora",
        choices=[{
            "index": 0,
            "message": {"role": "assistant", "content": text},
            "finish_reason": "stop",
        }],
        usage={
            "prompt_tokens": len(inputs.input_ids[0]),
            "completion_tokens": len(generated),
            "total_tokens": len(outputs[0]),
        },
    )


@app.get("/health")
@app.get("/v1/health/ready")
async def health():
    return {"status": "ok", "model_loaded": model is not None}


if __name__ == "__main__":
    port = int(os.getenv("TAAZI_LORA_PORT", "8001"))
    uvicorn.run("app.ai.serving.server:app", host="0.0.0.0", port=port, log_level="info")
