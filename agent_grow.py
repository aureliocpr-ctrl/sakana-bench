"""CRESCITA: fugu-ultra estende minilang (parte da base_minilang.py). 3 fasi guidate (potenze,
libreria stringhe, mappe) + loop di crescita AUTO-DIRETTA (Fugu sceglie le feature). Io sono il
regression-gate: le 22 acceptance originali + quelle delle fasi NON si devono rompere; se una feature
rompe e non si fixa, REVERT all'ultimo buono. Stop su crediti esauriti o cap chiamate. Spende crediti
su crescita reale. Salva minilang.py + transcript.json + added.txt."""
import os, json, time, subprocess, sys, urllib.request, re

KEY = os.environ["SK"]
BASE = "https://api.sakana.ai/v1"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
PRICE_IN, PRICE_OUT = 5.0, 30.0
MAX_CALLS = int(os.environ.get("MAX_CALLS", "15"))
spend = {"usd": 0.0, "calls": 0, "in": 0, "out": 0}
transcript = []
added = []

ORIG_ACCEPT = [
    ('print "hello world";', "hello world\n"), ("print 2 + 3 * 4;", "14\n"),
    ("let x = 10; let y = x * 2; print y;", "20\n"),
    ("let n = 7; if (n % 2 == 0) { print \"even\"; } else { print \"odd\"; }", "odd\n"),
    ("let i = 1; let s = 0; while (i <= 5) { s = s + i; i = i + 1; } print s;", "15\n"),
    ("fn fact(n) { if (n <= 1) { return 1; } return n * fact(n - 1); } print fact(5);", "120\n"),
    ("fn fib(n) { if (n < 2) { return n; } return fib(n-1) + fib(n-2); } print fib(10);", "55\n"),
    ('let a = "foo"; let b = "bar"; print a + b;', "foobar\n"),
    ("print (true && false) || !false;", "true\n"),
    ("let c = 0; let i = 0; while (i < 3) { c = c + i; i = i + 1; } print c;", "3\n"),
    ("print 5 > 3;", "true\n"), ("// c\nprint 1;\nprint 2;", "1\n2\n"),
    ("let a = [10, 20, 30]; print a[1];", "20\n"), ("let a = [1, 2, 3]; print len(a);", "3\n"),
    ("let a = [0, 0, 0]; a[2] = 9; print a[2];", "9\n"), ('print len("hello");', "5\n"),
    ("let s = 0; for (let i = 1; i <= 4; i = i + 1) { s = s + i; } print s;", "10\n"),
    ("let p = 1; for (let i = 1; i <= 5; i = i + 1) { p = p * i; } print p;", "120\n"),
    ('print "n=" + str(42);', "n=42\n"), ("print abs(0 - 7);", "7\n"),
    ("print max(3, 9);", "9\n"), ("print min(3, 9);", "3\n"),
]

PHASES = [
    ("power", "NEW: exponentiation operator '**' (right-associative, binds tighter than '+' '-' '*' '/').", [
        ("print 2 ** 10;", "1024\n"), ("print 2 ** 3 ** 2;", "512\n"), ("print 3 ** 2 + 1;", "10\n"),
    ]),
    ("strings", "NEW builtins on strings: upper(s) -> uppercase; lower(s) -> lowercase; "
                "substr(s, start, length) -> the substring of `length` chars starting at index `start` (0-based); "
                "index(s, sub) -> first index where `sub` occurs in `s`, or -1 if not present.", [
        ('print upper("abc");', "ABC\n"), ('print lower("XyZ");', "xyz\n"),
        ('print substr("hello", 1, 3);', "ell\n"), ('print index("hello", "ll");', "2\n"),
        ('print index("hello", "z");', "-1\n"),
    ]),
    ("maps", "NEW: map/dictionary values. Literal '{\"a\": 1, \"b\": 2}'. Indexing m[\"a\"]. Assignment "
             "m[\"k\"] = v (adds or updates). Builtin has(m, key) -> boolean. Empty map is '{}'.", [
        ('let m = {"x": 5, "y": 7}; print m["y"];', "7\n"),
        ('let m = {}; m["a"] = 9; print m["a"];', "9\n"),
        ('let m = {"a": 1}; print has(m, "a");', "true\n"),
        ('let m = {"a": 1}; print has(m, "z");', "false\n"),
    ]),
]


def ask_fugu(prompt_text):
    h = {"User-Agent": UA, "Accept": "text/event-stream", "Content-Type": "application/json",
         "Authorization": "Bearer " + KEY}
    data = {"model": "fugu-ultra", "input": prompt_text, "max_output_tokens": 16000,
            "reasoning": {"effort": "high"}, "stream": True}
    body = json.dumps(data).encode()
    for attempt in range(3):
        t0 = time.time(); text = []; final = None
        try:
            req = urllib.request.Request(BASE + "/responses", data=body, headers=h, method="POST")
            with urllib.request.urlopen(req, timeout=900) as r:
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
            out = "".join(text); usage = final.get("usage") if final else None
            if final and not out:
                for item in final.get("output", []):
                    for c in (item.get("content") or []):
                        if c.get("type") == "output_text":
                            out += c.get("text", "")
            spend["calls"] += 1
            if usage:
                it = usage.get("input_tokens", 0); ot = usage.get("output_tokens", 0)
                spend["in"] += it; spend["out"] += ot
                spend["usd"] += it / 1e6 * PRICE_IN + ot / 1e6 * PRICE_OUT
            print("  [call#%d] %.0fs out=%d cum~$%.2f" % (spend["calls"], time.time() - t0, len(out), spend["usd"]), flush=True)
            return out
        except Exception as e:
            msg = repr(e)
            print("  [fail] %s" % msg, flush=True)
            if any(w in msg.lower() for w in ("402", "quota", "insufficient", "billing", "credit", "payment")):
                raise RuntimeError("CREDIT_EXHAUSTED:" + msg)
            if attempt < 2:
                time.sleep(8)
    return None


def extract(ans):
    if not ans:
        return None
    s = ans.strip()
    if "```" in s:
        m = re.search(r"```(?:python)?\s*(.*?)```", s, re.S)
        if m:
            s = m.group(1).strip()
    return s


RUN_ONE = ("import sys,json,importlib.util\n"
           "src=open(sys.argv[2],encoding='utf-8').read()\n"
           "try:\n"
           "    sp=importlib.util.spec_from_file_location('minilang',sys.argv[1]+'/minilang.py')\n"
           "    m=importlib.util.module_from_spec(sp); sp.loader.exec_module(m)\n"
           "    print(json.dumps({'ok':True,'out':m.run(src)}))\n"
           "except Exception as e:\n"
           "    import traceback; print(json.dumps({'ok':False,'err':(repr(e)+' '+traceback.format_exc())[:400]}))\n")


def run_accept(code, accept_list, workdir):
    os.makedirs(workdir, exist_ok=True)
    open(os.path.join(workdir, "minilang.py"), "w", encoding="utf-8").write(code)
    open(os.path.join(workdir, "_run_one.py"), "w", encoding="utf-8").write(RUN_ONE)
    res = []
    for idx, (prog, expected) in enumerate(accept_list):
        pf = os.path.join(workdir, "_p%d.ml" % idx); open(pf, "w", encoding="utf-8").write(prog)
        try:
            r = subprocess.run([sys.executable, os.path.join(workdir, "_run_one.py"), workdir, pf],
                               capture_output=True, text=True, timeout=10)
            j = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {"ok": False, "err": "no-out:" + r.stderr[:150]}
        except subprocess.TimeoutExpired:
            j = {"ok": False, "err": "TIMEOUT"}
        except Exception as e:
            j = {"ok": False, "err": repr(e)}
        res.append({"prog": prog, "expected": expected, "got": j.get("out"), "err": j.get("err"),
                    "ok": bool(j.get("ok")) and j.get("out") == expected})
    return res


def fmt_fails(fails):
    return "\n\n".join("PROGRAM:\n%s\nEXPECTED: %r\nGOT: %r%s" %
                       (f["prog"], f["expected"], f["got"], ("  ERR:" + f["err"]) if f["err"] else "") for f in fails)


def main():
    wd = os.path.abspath("_gw")
    code = open("base_minilang.py", encoding="utf-8").read()
    cum = list(ORIG_ACCEPT)
    spec_extras = []
    try:
        # --- fasi guidate ---
        for name, delta, acc in PHASES:
            cum = cum + acc
            spec_extras.append(delta)
            print("\n== FASE %s (cum %d) ==" % (name, len(cum)), flush=True)
            for rnd in range(3):
                if spend["calls"] >= MAX_CALLS:
                    raise RuntimeError("CALL_CAP")
                if rnd == 0:
                    prompt = ("Here is the current minilang.py interpreter:\n\n" + code +
                              "\n\nEXTEND it to add this feature, keeping ALL existing behavior:\n" + delta +
                              "\nReturn ONLY the complete updated minilang.py (no fences, no prose).")
                else:
                    prompt = ("Current minilang.py:\n\n" + code + "\n\nThese cases FAIL:\n\n" +
                              fmt_fails([r for r in last if not r["ok"]]) +
                              "\n\nFix so all pass, keep existing behavior. Return ONLY the complete minilang.py.")
                cand = extract(ask_fugu(prompt))
                if not cand or "def run" not in cand:
                    continue
                last = run_accept(cand, cum, wd)
                npass = sum(1 for r in last if r["ok"])
                print("  %s r%d: %d/%d cum, ~$%.2f" % (name, rnd, npass, len(cum), spend["usd"]), flush=True)
                if npass == len(cum):
                    code = cand; break
            transcript.append({"stage": "phase:" + name, "pass": sum(1 for r in last if r["ok"]),
                               "total": len(cum), "calls": spend["calls"], "spend": round(spend["usd"], 3)})
            open("minilang.py", "w", encoding="utf-8").write(code)

        # --- crescita auto-diretta ---
        print("\n== CRESCITA AUTO-DIRETTA ==", flush=True)
        n = 0
        while spend["calls"] < MAX_CALLS:
            n += 1
            prompt = ("Here is the current minilang.py interpreter:\n\n" + code +
                      "\n\nYou are improving this language. Add ONE substantial, genuinely useful NEW capability "
                      "(e.g. a new builtin, a new control structure, first-class/lambda functions, closures, "
                      "try/catch error handling, a small standard-library function, etc.) that is NOT already present. "
                      "Do NOT remove or break ANY existing behavior. On the VERY FIRST line put a Python comment "
                      "'# ADDED: <one short line describing the new feature>'. Return ONLY the complete updated minilang.py.")
            cand = extract(ask_fugu(prompt))
            if not cand or "def run" not in cand:
                continue
            last = run_accept(cand, cum, wd)
            fails = [r for r in last if not r["ok"]]
            for fr in range(2):  # prova a fixare regressioni
                if not fails or spend["calls"] >= MAX_CALLS:
                    break
                cand2 = extract(ask_fugu("Current minilang.py:\n\n" + cand + "\n\nYour change BROKE these existing cases:\n\n" +
                                         fmt_fails(fails) + "\n\nFix WITHOUT removing your new feature. Return ONLY the complete minilang.py."))
                if cand2 and "def run" in cand2:
                    cand = cand2; last = run_accept(cand, cum, wd); fails = [r for r in last if not r["ok"]]
            desc = (cand.splitlines()[0] if cand.splitlines() and cand.splitlines()[0].startswith("#") else "# ADDED: (n/d)")
            if not fails:
                code = cand; added.append(desc); open("minilang.py", "w", encoding="utf-8").write(code)
                print("  grow#%d OK %s | regr %d/%d ~$%.2f" % (n, desc[:70], len(cum), len(cum), spend["usd"]), flush=True)
                transcript.append({"stage": "grow#%d" % n, "added": desc, "ok": True, "calls": spend["calls"], "spend": round(spend["usd"], 3)})
            else:
                print("  grow#%d SCARTATO (regressione non fixata), tengo il precedente ~$%.2f" % (n, spend["usd"]), flush=True)
                transcript.append({"stage": "grow#%d" % n, "added": desc, "ok": False, "calls": spend["calls"], "spend": round(spend["usd"], 3)})
            json.dump(transcript, open("transcript.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
            open("added.txt", "w", encoding="utf-8").write("\n".join(added))
    except RuntimeError as e:
        print("STOP:", e, flush=True)
        transcript.append({"stage": "stop", "reason": str(e)})

    open("minilang.py", "w", encoding="utf-8").write(code)
    json.dump(transcript, open("transcript.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    open("added.txt", "w", encoding="utf-8").write("\n".join(added))
    print("\n=== FINE === calls=%d ~$%.2f code_len=%d features_added=%d" % (spend["calls"], spend["usd"], len(code), len(added)), flush=True)


if __name__ == "__main__":
    main()
