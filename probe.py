"""Fase 2: risposte reali + usage da fugu/fugu-ultra. Key da env SK (mai stampata)."""
import os, json, urllib.request, urllib.error

key = os.environ["SK"]
base = "https://api.sakana.ai/v1"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def chat(model, content, mx=200):
    h = {"User-Agent": UA, "Accept": "application/json", "Content-Type": "application/json",
         "Authorization": "Bearer " + key}
    data = {"model": model, "messages": [{"role": "user", "content": content}], "max_tokens": mx}
    req = urllib.request.Request(base + "/chat/completions", data=json.dumps(data).encode(), headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return "ERR", repr(e)


QS = [
    ("factual", "What is the capital of Australia? Answer with one word."),
    ("false_premise", "In what year did Albert Einstein receive the Nobel Prize specifically for his theory of relativity? Answer concisely."),
]
for model in ["fugu", "fugu-ultra"]:
    for tag, q in QS:
        st, b = chat(model, q)
        print("\n=== %s | %s -> %s" % (model, tag, st))
        try:
            j = json.loads(b)
            msg = j["choices"][0]["message"]["content"]
            print("ANSWER:", msg.strip()[:600])
            print("USAGE:", j.get("usage"))
        except Exception as ex:
            print("RAW:", b[:500], "| parse-err", ex)
