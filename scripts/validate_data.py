#!/usr/bin/env python3
"""Cross-file consistency checks for quantum_veil/backend/data/. Run: python validate_data.py"""
import csv, os, re, sys

D = sys.argv[1] if len(sys.argv) > 1 else os.path.join("quantum_veil", "backend", "data")
ok = True


def check(cond, msg):
    global ok
    print(("PASS  " if cond else "FAIL  ") + msg)
    ok &= bool(cond)


def read(n):
    with open(os.path.join(D, n), encoding="utf-8") as f:
        return f.read()


def rows(n):
    with open(os.path.join(D, n), encoding="utf-8") as f:
        return list(csv.DictReader(f))


digits = lambda s: re.sub(r"\D", "", s)
firs = {n: read(n) for n in ("FIR_1_English.txt", "FIR_2_Hindi.txt", "FIR_3_English.txt")}
b1, b2 = rows("Bank_Logs_1.csv"), rows("Bank_Logs_2.csv")
c1, c2 = rows("CDR_Logs_1.csv"), rows("CDR_Logs_2.csv")

PX, IMEI_X = "9999900101", None
for r in c1:
    if r["caller_msisdn"] == "+91" + PX:
        IMEI_X = r["caller_imei"]; break

print("== Shared identifiers ==")
for n, t in firs.items():
    check(PX in digits(t), f"{n} contains shared phone {PX}")
    check(IMEI_X in t, f"{n} contains shared IMEI {IMEI_X}")
check(any(r["caller_imei"] == IMEI_X and r["caller_msisdn"] != "+91" + PX for r in c1), "CDR_1: IMEI_X used by a second SIM")
check(any(r["caller_imei"] == IMEI_X and r["caller_msisdn"] != "+91" + PX for r in c2), "CDR_2: IMEI_X used by a different SIM")
check(any("+91" + PX in (r["caller_msisdn"], r["callee_msisdn"]) for r in c1) and
      any("+91" + PX in (r["caller_msisdn"], r["callee_msisdn"]) for r in c2), "PX appears in both CDR files")

print("== Luhn on IMEIs ==")
def luhn(n):
    s = 0
    for i, ch in enumerate(reversed(n)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2; d -= 9 if d > 9 else 0
        s += d
    return s % 10 == 0
imeis = {r[k] for r in c1 + c2 for k in ("caller_imei", "callee_imei") if r[k]}
check(all(luhn(i) and len(i) == 15 for i in imeis), f"all {len(imeis)} IMEIs are 15 digits and Luhn-valid")

print("== FIR amounts vs Bank_Logs_1 ==")
victim_acc = {"FIR_1_English.txt": "309100458213", "FIR_2_Hindi.txt": "612300774590", "FIR_3_English.txt": "405500112367"}
for n, acc in victim_acc.items():
    total = sum(int(r["amount_inr"]) for r in b1 if r["from_account"] == acc)
    m = re.search(r"(?:Rs\.?|₹)\s?([\d,]+)", re.search(r"(?:Total amount reported lost|कुल ठगी की राशि):\s*(.*)", firs[n]).group(1))
    check(int(m.group(1).replace(",", "")) == total, f"{n}: reported amount = {total} = sum of Bank_Logs_1 for victim {acc}")
    utrs = set(re.findall(r"UTR\d+", firs[n]))
    bank_utrs = {r["utr_ref"] for r in b1 if r["from_account"] == acc}
    check(utrs == bank_utrs, f"{n}: UTR refs match bank log ({len(utrs)})")

print("== Bank conservation ==")
allr = sorted(b1 + b2, key=lambda r: r["timestamp"])
bal, victims = {}, set(victim_acc.values())
neg = False
for r in allr:
    a, b, amt = r["from_account"], r["to_account"], int(r["amount_inr"])
    if a not in victims:
        bal[a] = bal.get(a, 0) - amt
        neg |= bal[a] < 0
        check_bal = int(r["from_balance_after_inr"]) == bal[a]
        if not check_bal: neg = True
    bal[b] = bal.get(b, 0) + amt
    if int(r["to_balance_after_inr"]) != bal[b]: neg = True
check(not neg, "no overdrafts; all balance_after columns match recomputed running balances")
check(all(a in {r["to_account"] for r in b1 + b2} for a in [r["from_account"] for r in b2]), "every Bank_Logs_2 sender received funds earlier")
print("   Freeze ranking (remaining balance):")
for a, v in sorted(bal.items(), key=lambda kv: -kv[1]):
    print(f"     {a}  Rs {v:,}")

print("== Accounts mentioned in FIRs exist in bank logs ==")
bank_accs = {r[k] for r in b1 + b2 for k in ("from_account", "to_account")}
for n, t in firs.items():
    mentioned = set(re.findall(r"\b\d{12}\b", t))
    check(mentioned <= bank_accs, f"{n}: {len(mentioned)} account IDs all found in bank logs")

print("== Timeline sanity ==")
check(all(r["timestamp"] >= "2026-08-28" for r in c1 + c2), "CDR dates within range")
check(min(r["timestamp"] for r in c1) < min(r["timestamp"] for r in b1), "CDR contact precedes first transfer")

print("\nALL CHECKS PASSED" if ok else "\nSOME CHECKS FAILED")
sys.exit(0 if ok else 1)