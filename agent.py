"""AGENTE: fugu-ultra costruisce 'minilang' (interprete di un piccolo linguaggio) DA SOLO, in un
loop agentico TDD su runner US. Io fornisco spec + acceptance; Fugu progetta e scrive il codice,
l'harness esegue i test in subprocess isolati e rimanda i fallimenti finche' passa. Multi-fase
(core -> array -> for -> builtins -> polish) per consumare i crediti su lavoro reale.
Salva minilang.py finale + transcript.json. Tutto il pensiero/codice e' di Fugu."""
import os, json, time, subprocess, sys, urllib.request, re

KEY = os.environ["SK"]
BASE = "https://api.sakana.ai/v1"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
PRICE_IN, PRICE_OUT = 5.0, 30.0          # fugu-ultra USD / 1M tok
MAX_FIX_ROUNDS = 5                         # tentativi-fix per fase
spend = {"usd": 0.0, "calls": 0, "in": 0, "out": 0}
transcript = []

SPEC_CORE = r'''You are building an interpreter for a small programming language called "minilang", in Python.

Expose a top-level function:  run(source: str) -> str
It executes the minilang program in `source` and RETURNS all output produced by `print` statements
as a single string, each printed value followed by a newline "\n". Do NOT print to stdout; accumulate
and return the string.

minilang language specification (CORE):
- A program is a sequence of statements. Statements end with ';'. Blocks are delimited by '{' '}'.
  Whitespace is insignificant. Comments start with '//' and run to end of line.
- Values: integers, floats, booleans (true / false), strings (double-quoted "..."), and null.
- print EXPR;  -> append the value's text + "\n". Booleans -> "true"/"false". null -> "null".
  Integers print with NO decimal point (e.g. 14). Strings print their raw characters.
- Variables: 'let NAME = EXPR;' declares and assigns. 'NAME = EXPR;' reassigns an EXISTING variable
  (raise an error if it was never declared).
- Operators with the usual precedence (low to high): '||' , '&&' , comparisons (== != < <= > >=),
  '+' '-' , '*' '/' '%' , unary ('!' and unary '-'), then power is NOT required. Parentheses '(' ')'.
  '+' on two strings concatenates them. '&&' and '||' short-circuit and yield booleans.
- if (COND) { STMTS } else { STMTS }   (the else part is optional).
- while (COND) { STMTS } .
- Functions: 'fn NAME(p1, p2, ...) { STMTS }' with 'return EXPR;'. Recursion MUST work. A call is
  NAME(arg1, arg2). A function returns its 'return' value, or null if it falls off the end. Functions
  get a fresh local scope for parameters/locals but can see other top-level functions (for recursion).
- On ANY malformed program or runtime error (undefined variable, calling a non-function, wrong arity,
  type errors, etc.) raise a Python exception. The test harness treats an exception as a failed case.

Implement a real tokenizer + parser + tree-walking interpreter. Do NOT use eval/exec/ast.
Return ONLY the complete Python source code of minilang.py. No markdown fences, no prose.'''

# ----- fasi: (nome, delta-spec testuale, acceptance [(program, expected_output)]) -----
PHASES = [
    ("core", "", [
        ('print "hello world";', "hello world\n"),
        ("print 2 + 3 * 4;", "14\n"),
        ("let x = 10; let y = x * 2; print y;", "20\n"),
        ("let n = 7; if (n % 2 == 0) { print \"even\"; } else { print \"odd\"; }", "odd\n"),
        ("let i = 1; let s = 0; while (i <= 5) { s = s + i; i = i + 1; } print s;", "15\n"),
        ("fn fact(n) { if (n <= 1) { return 1; } return n * fact(n - 1); } print fact(5);", "120\n"),
        ("fn fib(n) { if (n < 2) { return n; } return fib(n-1) + fib(n-2); } print fib(10);", "55\n"),
        ('let a = "foo"; let b = "bar"; print a + b;', "foobar\n"),
        ("print (true && false) || !false;", "true\n"),
        ("let c = 0; let i = 0; while (i < 3) { c = c + i; i = i + 1; } print c;", "3\n"),
        ("print 5 > 3;", "true\n"),
        ("// a comment line\nprint 1;\nprint 2;", "1\n2\n"),
    ]),
    ("arrays", "EXTENSION 1 - arrays: array literals 'let a = [1, 2, 3];'; 0-based indexing 'a[0]'; "
               "element assignment 'a[i] = v;'; builtin 'len(x)' returns the length of an array OR a string.", [
        ("let a = [10, 20, 30]; print a[1];", "20\n"),
        ("let a = [1, 2, 3]; print len(a);", "3\n"),
        ("let a = [0, 0, 0]; a[2] = 9; print a[2];", "9\n"),
        ('print len("hello");', "5\n"),
    ]),
    ("for", "EXTENSION 2 - a C-style for loop: 'for (INIT; COND; STEP) { STMTS }' where INIT is a 'let' "
            "or an assignment, COND is a boolean expression, STEP is an assignment. Standard semantics.", [
        ("let s = 0; for (let i = 1; i <= 4; i = i + 1) { s = s + i; } print s;", "10\n"),
        ("let p = 1; for (let i = 1; i <= 5; i = i + 1) { p = p * i; } print p;", "120\n"),
    ]),
    ("builtins", "EXTENSION 3 - builtins: 'str(x)' converts any value to its string form (same text as "
                 "print would use); 'abs(x)'; 'max(a, b)'; 'min(a, b)'.", [
        ('print "n=" + str(42);', "n=42\n"),
        ("print abs(0 - 7);", "7\n"),
        ("print max(3, 9);", "9\n"),
        ("print min(3, 9);", "3\n"),
    ]),
]


def ask_fugu(prompt_text):
    """fugu-ultra via Responses API streaming. Ritorna (text, finish_status). Aggiorna spend."""
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
            out = "".join(text); st = None; usage = None
            if final:
                st = final.get("status"); usage = final.get("usage")
                if not out:
                    for item in final.get("output", []):
                        for c in (item.get("content") or []):
                            if c.get("type") == "output_text":
                                out += c.get("text", "")
            spend["calls"] += 1
            if usage:
                it = usage.get("input_tokens", 0); ot = usage.get("output_tokens", 0)
                spend["in"] += it; spend["out"] += ot
                spend["usd"] += it / 1e6 * PRICE_IN + ot / 1e6 * PRICE_OUT
            print("  [fugu-ultra call#%d] %.0fs out_len=%d status=%s ~$%.3f (cum ~$%.2f)"
                  % (spend["calls"], time.time() - t0, len(out), st, 0.0, spend["usd"]), flush=True)
            return out, st
        except Exception as e:
            msg = repr(e)
            print("  [fugu-ultra] attempt %d FAIL: %s" % (attempt + 1, msg), flush=True)
            if any(w in msg.lower() for w in ("402", "quota", "insufficient", "billing", "credit")):
                raise RuntimeError("CREDIT_EXHAUSTED:" + msg)
            if attempt < 2:
                time.sleep(8)
    return None, "error"


def extract(ans):
    if not ans:
        return None
    s = ans.strip()
    if "```" in s:
        m = re.search(r"```(?:python)?\s*(.*?)```", s, re.S)
        if m:
            s = m.group(1).strip()
    return s


RUN_ONE = r'''import sys, json, importlib.util
d, pf = sys.argv[1], sys.argv[2]
src = open(pf, encoding="utf-8").read()
try:
    spec = importlib.util.spec_from_file_location("minilang", d + "/minilang.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    out = m.run(src)
    print(json.dumps({"ok": True, "out": out}))
except Exception as e:
    import traceback
    print(json.dumps({"ok": False, "err": (repr(e) + " | " + traceback.format_exc())[:400]}))
'''


def run_accept(code, accept_list, workdir):
    os.makedirs(workdir, exist_ok=True)
    open(os.path.join(workdir, "minilang.py"), "w", encoding="utf-8").write(code)
    open(os.path.join(workdir, "_run_one.py"), "w", encoding="utf-8").write(RUN_ONE)
    results = []
    for idx, (prog, expected) in enumerate(accept_list):
        pf = os.path.join(workdir, "_p%d.ml" % idx)
        open(pf, "w", encoding="utf-8").write(prog)
        try:
            r = subprocess.run([sys.executable, os.path.join(workdir, "_run_one.py"), workdir, pf],
                               capture_output=True, text=True, timeout=10)
            j = json.loads((r.stdout or "").strip().splitlines()[-1]) if r.stdout.strip() else {"ok": False, "err": "no-output:" + r.stderr[:200]}
        except subprocess.TimeoutExpired:
            j = {"ok": False, "err": "TIMEOUT (probabile loop infinito)"}
        except Exception as e:
            j = {"ok": False, "err": "harness:" + repr(e)}
        ok = bool(j.get("ok")) and j.get("out") == expected
        results.append({"prog": prog, "expected": expected, "got": j.get("out"), "err": j.get("err"), "ok": ok})
    return results


def fmt_fails(fails):
    out = []
    for f in fails:
        out.append("PROGRAM:\n%s\nEXPECTED stdout: %r\nGOT: %r%s" %
                   (f["prog"], f["expected"], f["got"], ("  ERROR: " + f["err"]) if f["err"] else ""))
    return "\n\n".join(out)


def main():
    workdir = os.path.abspath("_mlwork")
    code = None
    unlocked_spec = SPEC_CORE
    cum_accept = []
    try:
        for pi, (name, delta, accept) in enumerate(PHASES):
            cum_accept = cum_accept + accept
            if delta:
                unlocked_spec = unlocked_spec + "\n\n" + delta
            print("\n===== FASE %d: %s (%d acceptance cumulativi) =====" % (pi, name, len(cum_accept)), flush=True)
            for rnd in range(MAX_FIX_ROUNDS):
                if code is None:
                    prompt = unlocked_spec + "\n\nReturn ONLY the complete minilang.py."
                elif rnd == 0:
                    prompt = (unlocked_spec + "\n\nHere is the current working minilang.py:\n\n" + code +
                              "\n\nEXTEND it to satisfy the new EXTENSION above while keeping ALL existing "
                              "behavior intact. Return ONLY the complete, updated minilang.py.")
                else:
                    fails = [r for r in last_results if not r["ok"]]
                    prompt = (unlocked_spec + "\n\nHere is your current minilang.py:\n\n" + code +
                              "\n\nThese cases FAIL:\n\n" + fmt_fails(fails) +
                              "\n\nFix the code so ALL cases pass. Return ONLY the complete corrected minilang.py.")
                ans, st = ask_fugu(prompt)
                cand = extract(ans)
                if not cand or "def run" not in cand:
                    print("  round %d: NESSUN codice valido (status=%s)" % (rnd, st), flush=True)
                    transcript.append({"phase": name, "round": rnd, "event": "no_code", "status": st})
                    continue
                code = cand
                last_results = run_accept(code, cum_accept, workdir)
                npass = sum(1 for r in last_results if r["ok"])
                print("  round %d: %d/%d acceptance, ~$%.2f spesi" % (rnd, npass, len(cum_accept), spend["usd"]), flush=True)
                transcript.append({"phase": name, "round": rnd, "pass": npass, "total": len(cum_accept),
                                   "spend_usd": round(spend["usd"], 3), "code_len": len(code)})
                # salva progressi sempre
                open("minilang.py", "w", encoding="utf-8").write(code)
                json.dump(transcript, open("transcript.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
                if npass == len(cum_accept):
                    print("  FASE %s OK." % name, flush=True)
                    break
            else:
                print("  FASE %s NON completata in %d round (continuo comunque)." % (name, MAX_FIX_ROUNDS), flush=True)
    except RuntimeError as e:
        print("STOP:", e, flush=True)
        transcript.append({"event": "stop", "reason": str(e)})

    if code:
        open("minilang.py", "w", encoding="utf-8").write(code)
    json.dump(transcript, open("transcript.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("\n=== FINE === calls=%d  ~$%.2f  in=%d out=%d  code_len=%d"
          % (spend["calls"], spend["usd"], spend["in"], spend["out"], len(code or "")), flush=True)


if __name__ == "__main__":
    main()
