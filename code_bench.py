"""Lato Fugu del field-test coding: manda code_prompt.txt a fugu + fugu-ultra, salva le impl in code_results.json."""
import os, json, time, urllib.request, urllib.error

key = os.environ["SK"]
base = "https://api.sakana.ai/v1"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
prompt = os.environ.get("CODE_PROMPT") or open("code_prompt.txt", encoding="utf-8").read()


def chat(model, content, mx):
    h = {"User-Agent": UA, "Accept": "application/json", "Content-Type": "application/json",
         "Authorization": "Bearer " + key}
    data = {"model": model, "messages": [{"role": "user", "content": content}], "max_tokens": mx, "temperature": 0}
    body = json.dumps(data).encode()
    for attempt in range(3):
        req = urllib.request.Request(base + "/chat/completions", data=body, headers=h, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            code, txt = e.code, e.read().decode("utf-8", "replace")
            if code in (429, 500, 502, 503, 529) and attempt < 2:
                time.sleep(4 * (attempt + 1)); continue
            return code, txt
        except Exception as e:
            if attempt < 2:
                time.sleep(3); continue
            return "ERR", repr(e)
    return "ERR", "exhausted"


out = {}
for model in ("fugu", "fugu-ultra"):
    st, b = chat(model, prompt, 3500)
    ans = usage = err = None
    try:
        j = json.loads(b)
        ans = j["choices"][0]["message"]["content"]
        usage = j.get("usage")
    except Exception:
        err = "%s:%s" % (st, b[:300])
    out[model] = {"answer": ans, "usage": usage, "err": err, "status": st}
    print(model, "->", st, "| len:", len(ans or ""), "| err:", err)

json.dump(out, open("code_results.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print("saved code_results.json")
