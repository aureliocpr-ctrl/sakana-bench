"""Lato Fugu del bench: per ogni task chiama fugu + fugu-ultra, salva results.json + cost tally.
Key da env SK (mai stampata). Gira su runner US (Actions)."""
import os, json, time, urllib.request, urllib.error

key = os.environ["SK"]
base = "https://api.sakana.ai/v1"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
# prezzi pubblici USD/1M token (verificare col credito reale): input / output
PRICE = {
    "fugu": (0.50, 2.00),         # stima mini (non pubblicato preciso): conservativa
    "fugu-ultra": (5.00, 30.00),  # pubblicato
}
MAXTOK = {"fugu": 512, "fugu-ultra": 1400}


def chat(model, content, mx):
    h = {"User-Agent": UA, "Accept": "application/json", "Content-Type": "application/json",
         "Authorization": "Bearer " + key}
    data = {"model": model, "messages": [{"role": "user", "content": content}], "max_tokens": mx}
    body = json.dumps(data).encode()
    for attempt in range(3):
        req = urllib.request.Request(base + "/chat/completions", data=body, headers=h, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            code = e.code
            txt = e.read().decode("utf-8", "replace")
            if code in (429, 500, 502, 503, 529) and attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            return code, txt
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
                continue
            return "ERR", repr(e)
    return "ERR", "exhausted"


tasks = json.load(open("tasks.json", encoding="utf-8"))
out = []
cost = {"fugu": 0.0, "fugu-ultra": 0.0}
for t in tasks:
    rec = {"id": t["id"], "axis": t["axis"], "q": t["q"], "gold": t["gold"]}
    for model in ("fugu", "fugu-ultra"):
        st, b = chat(model, t["q"], MAXTOK[model])
        ans = usage = err = None
        try:
            j = json.loads(b)
            ans = j["choices"][0]["message"]["content"]
            usage = j.get("usage")
            if usage:
                pin, pout = PRICE[model]
                cost[model] += usage.get("prompt_tokens", 0) / 1e6 * pin
                cost[model] += usage.get("completion_tokens", 0) / 1e6 * pout
                # orchestration input billed at input rate (single-rate, non-stacked)
                det = usage.get("prompt_tokens_details", {}) or {}
                cost[model] += det.get("orchestration_input_tokens", 0) / 1e6 * pin
        except Exception:
            err = "%s:%s" % (st, b[:200])
        rec[model] = {"answer": ans, "usage": usage, "err": err, "status": st}
        time.sleep(0.4)
    out.append(rec)
    print("done", t["id"], t["axis"],
          "| fugu:", (rec["fugu"]["answer"] or rec["fugu"]["err"] or "")[:40].replace("\n", " "),
          "| ultra:", (rec["fugu-ultra"]["answer"] or rec["fugu-ultra"]["err"] or "")[:40].replace("\n", " "))

json.dump(out, open("results.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print("\n=== COST ESTIMATE (USD) ===")
print("fugu       ~$%.4f" % cost["fugu"])
print("fugu-ultra ~$%.4f" % cost["fugu-ultra"])
print("TOTAL      ~$%.4f" % (cost["fugu"] + cost["fugu-ultra"]))
print("items:", len(out))
