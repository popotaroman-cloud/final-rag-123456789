import ast
import json
import logging
import re

import httpx
from fastapi import FastAPI, HTTPException

from . import config, ollama_client, prompts
from .rag import KnowledgeStore
from .schemas import (
    AskRequest,
    AskResponse,
    CodeRequest,
    CodeResponse,
    KnowledgeRequest,
    KnowledgeResponse,
    Source,
)

log = logging.getLogger("student-rag")
app = FastAPI(title="Student RAG Service", version=config.VERSION)
store = KnowledgeStore()

_CODE_BLOCK = re.compile(r"```(?:python|py)?[ \t]*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def _ollama_error(exc: Exception) -> HTTPException:
    log.exception("Ollama call failed")
    return HTTPException(status_code=502, detail=f"LLM backend error: {exc}")


def _match_key(text: str, keys: list[str]) -> str | None:
    text = text.strip()
    if text in keys:
        return text
    for key in keys:
        # "ค." or "ค) ..." counts, but "คำตอบ..." must not match the key "ค"
        if text.startswith(key) and (len(text) == len(key) or text[len(key)] in ".): "):
            return key
    return None


def parse_answer(raw: str, keys: list[str]) -> str:
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            found = _match_key(str(data.get("answer", "")), keys)
            if found:
                return found
    except json.JSONDecodeError:
        pass
    match = re.search(r'"answer"\s*:\s*"([^"]+)"', raw)
    if match:
        found = _match_key(match.group(1), keys)
        if found:
            return found
    log.warning("Could not parse an option key from: %r", raw[:200])
    return keys[0]


def extract_code(raw: str) -> str:
    match = _CODE_BLOCK.search(raw)
    return (match.group(1) if match else raw).strip() + "\n"


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "student_id": config.MANIFEST["student_id"],
        "llm_model": config.LLM_MODEL,
        "embed_model": config.EMBED_MODEL,
        "version": config.VERSION,
    }


@app.post("/knowledge", response_model=KnowledgeResponse)
def add_knowledge(req: KnowledgeRequest) -> KnowledgeResponse:
    try:
        chunks = store.add(req.namespace, [(d.doc_id, d.content) for d in req.documents])
    except httpx.HTTPError as exc:
        raise _ollama_error(exc)
    return KnowledgeResponse(namespace=req.namespace, documents=len(req.documents), chunks=chunks)


@app.delete("/knowledge/{namespace}")
def delete_knowledge(namespace: str) -> dict:
    return {"namespace": namespace, "deleted": store.delete(namespace)}


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    options = [(o.key, o.text) for o in req.options]
    keys = [k for k, _ in options]
    query = req.question + "\n" + "\n".join(text for _, text in options)
    answer_schema = {
        "type": "object",
        "properties": {"reason": {"type": "string"}, "answer": {"type": "string", "enum": keys}},
        "required": ["reason", "answer"],
    }
    try:
        hits = store.search(req.namespace, query, config.TOP_K)
        raw = ollama_client.chat(
            [
                {"role": "system", "content": prompts.MC_SYSTEM},
                {"role": "user", "content": prompts.mc_user_prompt(req.question, options, hits)},
            ],
            response_format=answer_schema,
        )
    except httpx.HTTPError as exc:
        raise _ollama_error(exc)
    return AskResponse(
        question_id=req.question_id,
        answer=parse_answer(raw, keys),
        sources=[Source(doc_id=c.doc_id, text=c.text, score=round(s, 4)) for c, s in hits],
    )


@app.post("/code", response_model=CodeResponse)
def write_code(req: CodeRequest) -> CodeResponse:
    if req.language.lower() != "python":
        raise HTTPException(status_code=400, detail="Only python is supported")
    try:
        hits = store.search(req.namespace, req.requirement, config.TOP_K)
        messages = [
            {"role": "system", "content": prompts.CODE_SYSTEM},
            {
                "role": "user",
                "content": prompts.code_user_prompt(req.requirement, req.signature, req.entry_point, hits),
            },
        ]
        raw = ollama_client.chat(messages)
        code = extract_code(raw)
        try:
            ast.parse(code)
        except SyntaxError as err:
            messages += [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": prompts.code_retry_prompt(str(err))},
            ]
            raw = ollama_client.chat(messages)
            code = extract_code(raw)
    except httpx.HTTPError as exc:
        raise _ollama_error(exc)
    return CodeResponse(task_id=req.task_id, language="python", code=code)
