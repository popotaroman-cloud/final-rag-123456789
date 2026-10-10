from .rag import Chunk

MC_SYSTEM = """You answer multiple-choice exam questions.
Use the reference documents as your primary source: when they contain the relevant facts, \
your answer must agree with them even if it contradicts what you believe in general.
If the documents do not cover the question, answer from your own knowledge.
Reply with JSON only, in the form {"reason": "...", "answer": "<option key>"}.
Keep "reason" to one or two short sentences. "answer" must be exactly one of the option keys."""

CODE_SYSTEM = """You are a careful Python programmer.
Write one complete, self-contained Python module that satisfies the requirement.
- Use only the Python standard library.
- Define the requested function with exactly the given name and parameters.
- Do not read input, print output, or run code at import time unless the requirement asks for it.
- When reference documents are provided, follow the rules they define exactly.
Reply with a single ```python code block and nothing else."""


def format_context(hits: list[tuple[Chunk, float]]) -> str:
    if not hits:
        return "(no reference documents)"
    blocks = []
    for n, (chunk, _score) in enumerate(hits, start=1):
        blocks.append(f"[{n}] ({chunk.doc_id})\n{chunk.text}")
    return "\n\n".join(blocks)


def mc_user_prompt(question: str, options: list[tuple[str, str]], hits) -> str:
    option_lines = "\n".join(f"{key}. {text}" for key, text in options)
    keys = ", ".join(key for key, _ in options)
    return (
        f"Reference documents:\n{format_context(hits)}\n\n"
        f"Question:\n{question}\n\n"
        f"Options:\n{option_lines}\n\n"
        f'Return JSON: {{"reason": "...", "answer": "<one of: {keys}>"}}'
    )


def code_user_prompt(requirement: str, signature: str | None, entry_point: str | None, hits) -> str:
    parts = []
    if hits:
        parts.append(f"Reference documents:\n{format_context(hits)}")
    parts.append(f"Requirement:\n{requirement}")
    if signature:
        parts.append(f"Use exactly this signature:\n{signature}")
    elif entry_point:
        parts.append(f"The function must be named `{entry_point}`.")
    return "\n\n".join(parts)


def code_retry_prompt(error: str) -> str:
    return (
        f"Your previous code does not compile: {error}\n"
        "Fix it and reply again with a single ```python code block."
    )
