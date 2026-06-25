"""fugu-ultra FATTO BENE: Responses API (/v1/responses) streaming + reasoning.effort.
La doc ufficiale usa questa interfaccia per fugu-ultra; qui l'orchestrazione non starva l'output visibile."""
import os, json, time, urllib.request

key = os.environ["SK"]
base = "https://api.sakana.ai/v1"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
prompt = os.environ.get("CODE_PROMPT") or open("code_prompt.txt", encoding="utf-8").read()


def responses_stream(model, inp, mx, effort, timeout_s):
    h = {"User-Agent": UA, "Accept": "text/event-stream", "Content-Type": "application/json",
         "Authorization": "Bearer " + key}
    data = {"model": model, "input": inp, "max_output_tokens": mx,
            "reasoning": {"effort": effort}, "stream": True}
    body = json.dumps(data).encode()
    t0 = time.time(); text = []; final = None; types = {}
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
                j = json.loads(p)
                t = j.get("type", "")
                types[t] = types.get(t, 0) + 1
                if t.endswith("output_text.delta") and j.get("delta"):
                    text.append(j["delta"])
                if t in ("response.completed", "response.incomplete", "response.failed"):
                    final = j.get("response")
            except Exception:
                pass
    out = "".join(text)
    status = incomplete = None
    if final:
        status = final.get("status")
        incomplete = final.get("incomplete_details")
        if not out:  # fallback: pesca output_text dal final
            for item in final.get("output", []):
                for c in (item.get("content") or []):
                    if c.get("type") == "output_text":
                        out += c.get("text", "")
    print("[%s] %.0fs len=%d status=%s incomplete=%s types=%s"
          % (model, time.time() - t0, len(out), status, incomplete, types), flush=True)
    return out, status, incomplete


ans = err = status = None
for attempt in range(2):
    try:
        ans, status, _inc = responses_stream("fugu-ultra", prompt, 16000, "high", 900)
        break
    except Exception as e:
        err = repr(e)
        print("[fugu-ultra] attempt %d FAIL: %s" % (attempt + 1, err), flush=True)
        if attempt < 1:
            time.sleep(8)

json.dump({"fugu-ultra": {"answer": ans, "status": status or ("ERR" if err else None),
                          "err": err, "via": "responses-stream", "has_def": "def apply_edit(" in (ans or "")}},
          open("ultra_results.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print("saved | has_def:", "def apply_edit(" in (ans or ""), flush=True)
