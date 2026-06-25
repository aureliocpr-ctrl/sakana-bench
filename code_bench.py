"""Lato Fugu coding (v2 STREAMING): SSE tiene viva la connessione (fix RemoteDisconnected del conductor)
+ max_tokens ampio. Salva code_results.json. Prompt da secret CODE_PROMPT."""
import os, json, time, urllib.request, urllib.error

key = os.environ["SK"]
base = "https://api.sakana.ai/v1"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
prompt = os.environ.get("CODE_PROMPT") or open("code_prompt.txt", encoding="utf-8").read()


def chat_stream(model, content, mx):
    h = {"User-Agent": UA, "Accept": "text/event-stream", "Content-Type": "application/json",
         "Authorization": "Bearer " + key}
    data = {"model": model, "messages": [{"role": "user", "content": content}],
            "max_tokens": mx, "temperature": 0, "stream": True}
    body = json.dumps(data).encode()
    for attempt in range(4):
        req = urllib.request.Request(base + "/chat/completions", data=body, headers=h, method="POST")
        chunks, usage, finish = [], None, None
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                for raw in r:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        j = json.loads(payload)
                        ch = (j.get("choices") or [{}])[0]
                        delta = ch.get("delta") or {}
                        if delta.get("content"):
                            chunks.append(delta["content"])
                        if ch.get("finish_reason"):
                            finish = ch["finish_reason"]
                        if j.get("usage"):
                            usage = j["usage"]
                    except Exception:
                        pass
            return 200, "".join(chunks), usage, finish
        except Exception as e:
            if attempt < 3:
                time.sleep(5 * (attempt + 1)); continue
            return "ERR", repr(e), None, None
    return "ERR", "exhausted", None, None


out = {}
for model in ("fugu", "fugu-ultra"):
    st, ans, usage, finish = chat_stream(model, prompt, 8000)
    out[model] = {"answer": ans, "usage": usage, "status": st, "finish_reason": finish}
    print(model, "->", st, "| len:", len(ans or ""), "| finish:", finish,
          "| has_def:", "def apply_edit(" in (ans or ""))

json.dump(out, open("code_results.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print("saved code_results.json")
