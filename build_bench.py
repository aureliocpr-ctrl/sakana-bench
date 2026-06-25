"""Build-from-scratch (calc.py): fugu via chat/completions streaming, fugu-ultra via Responses API.
Salva build_results.json. Prompt = build_prompt.txt (generico, nel repo)."""
import os, json, time, urllib.request

key = os.environ["SK"]
base = "https://api.sakana.ai/v1"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
prompt = open("build_prompt.txt", encoding="utf-8").read()


def chat_stream(model, content, mx, timeout_s):
    h = {"User-Agent": UA, "Accept": "text/event-stream", "Content-Type": "application/json",
         "Authorization": "Bearer " + key}
    data = {"model": model, "messages": [{"role": "user", "content": content}],
            "max_tokens": mx, "temperature": 0, "stream": True}
    body = json.dumps(data).encode()
    for attempt in range(2):
        t0 = time.time(); chunks = []; finish = None
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
                    except Exception:
                        pass
            print("[%s] %.0fs len=%d finish=%s" % (model, time.time() - t0, len("".join(chunks)), finish), flush=True)
            return "".join(chunks), finish
        except Exception as e:
            print("[%s] attempt %d FAIL: %r" % (model, attempt + 1, e), flush=True)
            if attempt < 1:
                time.sleep(6)
    return None, "error"


def responses_stream(model, inp, mx, effort, timeout_s):
    h = {"User-Agent": UA, "Accept": "text/event-stream", "Content-Type": "application/json",
         "Authorization": "Bearer " + key}
    data = {"model": model, "input": inp, "max_output_tokens": mx, "reasoning": {"effort": effort}, "stream": True}
    body = json.dumps(data).encode()
    for attempt in range(2):
        t0 = time.time(); text = []; final = None
        try:
            req = urllib.request.Request(base + "/responses", data=body, headers=h, method="POST")
            with urllib.request.urlopen(req, timeout=timeout_s) as r:
                for raw in r:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:"):
                        continue
                    p = line[5:].strip()
                    if p == "[DONE]":
                        break
                    try:
                        j = json.loads(p); t = j.get("type", "")
                        if t.endswith("output_text.delta") and j.get("delta"):
                            text.append(j["delta"])
                        if t in ("response.completed", "response.incomplete", "response.failed"):
                            final = j.get("response")
                    except Exception:
                        pass
            out = "".join(text)
            st = final.get("status") if final else None
            if not out and final:
                for item in final.get("output", []):
                    for c in (item.get("content") or []):
                        if c.get("type") == "output_text":
                            out += c.get("text", "")
            print("[%s] %.0fs len=%d status=%s" % (model, time.time() - t0, len(out), st), flush=True)
            return out, st
        except Exception as e:
            print("[%s] attempt %d FAIL: %r" % (model, attempt + 1, e), flush=True)
            if attempt < 1:
                time.sleep(8)
    return None, "error"


out = {}
a1, f1 = responses_stream("fugu-ultra", prompt, 16000, "high", 900)
out["fugu-ultra"] = {"answer": a1, "finish": f1, "via": "responses"}
print("fugu-ultra has_def:", "def evaluate(" in (a1 or ""), flush=True)

a2, f2 = chat_stream("fugu", prompt, 12000, 480)
out["fugu"] = {"answer": a2, "finish": f2, "via": "chat"}
print("fugu has_def:", "def evaluate(" in (a2 or ""), flush=True)

json.dump(out, open("build_results.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print("saved", flush=True)
