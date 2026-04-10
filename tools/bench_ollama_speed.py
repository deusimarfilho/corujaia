"""Mede tokens/s do Ollama para o modelo configurado (chat)."""
import json
import sys
import urllib.request

OLLAMA = "http://127.0.0.1:11434"


def bench(model: str, prompt: str) -> None:
    body = json.dumps(
        {"model": model, "prompt": prompt, "stream": False}
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    ec = int(data.get("eval_count") or 0)
    ed = int(data.get("eval_duration") or 0)
    td = int(data.get("total_duration") or 0)
    tps = (ec / (ed / 1e9)) if ed else 0.0

    print("model:", data.get("model", model))
    print("eval_count (tokens gerados):", ec)
    print("eval_duration_s:", round(ed / 1e9, 2))
    print("tokens_por_segundo:", round(tps, 2))
    print("total_duration_s:", round(td / 1e9, 2))


if __name__ == "__main__":
    model = sys.argv[1] if len(sys.argv) > 1 else "gemma4:26b"
    prompt = (
        sys.argv[2]
        if len(sys.argv) > 2
        else "Responda em uma unica frase: qual a capital do Ceara?"
    )
    bench(model, prompt)
