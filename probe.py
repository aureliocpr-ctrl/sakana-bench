"""Probe Sakana da runner US: paese egress + /models + ping. Key da env SK (mai stampata)."""
import os, json, urllib.request, urllib.error

key = os.environ.get("SK", "")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def call(url, data=None, auth=False):
    h = {"User-Agent": UA, "Accept": "application/json", "Content-Type": "application/json"}
    if auth and key:
        h["Authorization"] = "Bearer " + key
    body = json.dumps(data).encode() if data is not None else None
    method = "POST" if data is not None else "GET"
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return "ERR", repr(e)


st, b = call("https://ipinfo.io/json")
print("== IPINFO ->", st)
print(b[:250])
print("key set:", bool(key))

for base in ["https://api.sakana.ai/v1", "https://api.sakana.ai/openai/v1"]:
    st, b = call(base + "/models", auth=True)
    print("\n== GET", base + "/models ->", st)
    print(b[:1200])
    ids = []
    try:
        ids = [m.get("id") for m in json.loads(b).get("data", [])]
    except Exception:
        pass
    if isinstance(st, int) and st == 200 and ids:
        print("MODEL IDS:", ids)
        mid = "fugu" if "fugu" in ids else ids[0]
        st2, b2 = call(base + "/chat/completions", {
            "model": mid,
            "messages": [{"role": "user", "content": "Reply with exactly the single word: PONG"}],
            "max_tokens": 12,
        }, auth=True)
        print("== CHAT [", mid, "] ->", st2)
        print(b2[:800])
        break
