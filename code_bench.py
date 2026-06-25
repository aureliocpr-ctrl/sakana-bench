"""Coding v3 (bounded+diagnostico): fugu-ultra PRIMA, streaming SSE, 1 retry, max_tokens 4000, timing/modello."""
import os, json, time, urllib.request

key = os.environ["SK"]
base = "https://api.sakana.ai/v1"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
prompt = os.environ.get("CODE_PROMPT") or open("code_prompt.txt", encoding="utf-8").read()


def chat_stream(model, content, mx, timeout_s):
    h = {"User-Agent": UA, "Accept": "text/event-stream", "Content-Type": "application/json",
         "Authorization": "Bearer " + key}
    data = {"model": model, "messages": [{"role": "user", "content": content}],
            "max_tokens": mx, "temperature": 0, "stream": True}
    body = json.dumps(data).encode()
    for attempt in range(2):
        print("[%s] attempt %d ..." % (model, attempt + 1), flush=True)
        t0 = time.time(); chunks = []; usage = None; finish = None
        try:
            req = urllib.request.Request(base + "/chat/completions", data=body, headers=h, method="POST")
            with urllib.request.urlopen(req, timeout=timeout_s) as r:
                for raw in r:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:"):
                        continue
                    p = line[5:].strip()
                    if p == "[DONE]":
                        break
                    try:
                        j = json.loads(p); ch = (j.get("choices") or [{}])[0]; d = ch.get("delta") or {}
                        if d.get("content"):
                            chunks.append(d["content"])
                        if ch.get("finish_reason"):
                            finish = ch["finish_reason"]
                        if j.get("usage"):
                            usage = j["usage"]
                    except Exception:
                        pass
            print("[%s] done %.0fs len=%d finish=%s" % (model, time.time() - t0, len("".join(chunks)), finish), flush=True)
            return 200, "".join(chunks), usage, finish
        except Exception as e:
            print("[%s] attempt %d FAIL %.0fs: %r" % (model, attempt + 1, time.time() - t0, e), flush=True)
            if attempt < 1:
                time.sleep(5); continue
            return "ERR", repr(e), None, None
    return "ERR", "exhausted", None, None


out = {}
for model in ("fugu-ultra", "fugu"):
    st, ans, usage, finish = chat_stream(model, prompt, 4000, 300)
    out[model] = {"answer": ans, "usage": usage, "status": st, "finish_reason": finish}
    print(model, "->", st, "len", len(ans or ""), "has_def", "def apply_edit(" in (ans or ""), flush=True)

json.dump(out, open("code_results.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print("saved", flush=True)
