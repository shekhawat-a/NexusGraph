#!/usr/bin/env python3
"""
NexusGraph synthetic data generator (Team Quantum Veil, Build With Bharat 4.0)
All people, banks, phone numbers, IMEIs and accounts are FICTIONAL.
Run from the folder that contains `quantum_veil/`:
    python generate_data.py            # writes quantum_veil/backend/data/*
Single source of truth: every FIR / CSV value comes from the dicts below.
"""
import csv
import os
import sys
from datetime import datetime

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join("quantum_veil", "backend", "data")
os.makedirs(OUT, exist_ok=True)


# ---------------------------------------------------------------- helpers
def luhn_check_digit(digits14: str) -> str:
    total = 0
    for i, ch in enumerate(reversed(digits14)):
        d = int(ch)
        if i % 2 == 0:          # double every 2nd digit from the right (of the 14-digit body)
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return str((10 - total % 10) % 10)


def make_imei(body14: str) -> str:
    assert len(body14) == 14
    return body14 + luhn_check_digit(body14)


def inr(n: int) -> str:
    """Indian digit grouping: 486500 -> 4,86,500"""
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts + [tail])


def ts(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M")


# ---------------------------------------------------------------- phones (10-digit, canonical form in CSVs = +91XXXXXXXXXX)
PH = {
    "PX":   "9999900101",   # PLANTED SHARED PHONE (handler "Vicky") - appears in all 3 FIRs
    "SIMB": "9999900102",   # second SIM used in UP loan-app case
    "SIMC": "9999900103",   # third SIM used in Pune investment case
    "PM":   "9999900001",   # master controller's phone (never in a FIR; found via CDR)
    "V1":   "9999900211", "V2": "9999900222", "V3": "9999900233",
    "M1":   "9999900301", "M2": "9999900302", "M3": "9999900303",
    "M4":   "9999900304", "M5": "9999900305", "M6": "9999900306",
    "N1":   "9999900901", "N2": "9999900902", "N3": "9999900903",   # unrelated noise
}
HELPLINE = "1930"   # real national cyber-crime helpline - legit hub, should NOT be treated as a suspect

# ---------------------------------------------------------------- devices
IMEI_X = make_imei("86000100200300")   # PLANTED SHARED IMEI (suspect handset, rotated SIMs PX/SIMB/SIMC)
IMEI_Y = make_imei("86000100200400")   # master controller handset
IMEI = {
    "PX": IMEI_X, "SIMB": IMEI_X, "SIMC": IMEI_X, "PM": IMEI_Y,
    "V1": make_imei("35100000000011"), "V2": make_imei("35100000000022"), "V3": make_imei("35100000000033"),
    "M1": make_imei("35200000000001"), "M2": make_imei("35200000000002"), "M3": make_imei("35200000000003"),
    "M4": make_imei("35200000000004"), "M5": make_imei("35200000000005"), "M6": make_imei("35200000000006"),
    "N1": make_imei("35300000000001"), "N2": make_imei("35300000000002"), "N3": make_imei("35300000000003"),
}
LOC = {
    "PX": "Jaipur, RJ", "SIMB": "Jaipur, RJ", "SIMC": "Jaipur, RJ", "PM": "Jaipur, RJ",
    "V1": "Bengaluru, KA", "V2": "Noida, UP", "V3": "Pune, MH",
    "M1": "Hubballi, KA", "M2": "Dehradun, UK", "M3": "Meerut, UP",
    "M4": "Haridwar, UK", "M5": "Kolhapur, MH", "M6": "Solapur, MH",
    "N1": "Bengaluru, KA", "N2": "Lucknow, UP", "N3": "Pune, MH",
}

# ---------------------------------------------------------------- bank accounts
ACC = {
    "V1": ("309100458213", "Rohan Deshpande", "Nirmal Bank"),
    "V2": ("612300774590", "Sunita Verma", "Sagar Co-op Bank"),
    "V3": ("405500112367", "Meera Kulkarni", "Kaveri Bank"),
    "M1": ("778200314456", "Pradeep Naik", "Anvay Small Finance Bank"),
    "M2": ("520900663128", "Gaurav Bisht", "Tarang Payments Bank"),
    "M3": ("611800229047", "Anil Rawat", "Sagar Co-op Bank"),
    "M4": ("733400581902", "Sandeep Tomar", "Mahi Gramin Bank"),
    "M5": ("420600917735", "Kishore Patil", "Kaveri Bank"),
    "M6": ("774100846021", "Ravi Chavan", "Anvay Small Finance Bank"),
    "I1": ("888100300415", "Shree Balaji Traders", "Nirmal Bank"),
    "I2": ("888200300526", "Om Digital Enterprises", "Sagar Co-op Bank"),
    "I3": ("888300300637", "Lakshya Consultancy Services", "Kaveri Bank"),
    "MASTER": ("999100200018", "Neelkanth Trading Co.", "Nirmal Bank"),
    "EXCH": ("555000123456", "CoinBazaar Demo Exchange (Omnibus)", "Tarang Payments Bank"),
}
VICTIMS = {"V1", "V2", "V3"}

# ---------------------------------------------------------------- transactions (single source of truth)
# (txn_id, timestamp, from, to, amount, channel, remarks)
BANK_1 = [  # victim -> mule
    ("T001", "2026-09-01 10:14", "V1", "M1", 50000,  "UPI",  "Task deposit 1"),
    ("T002", "2026-09-01 11:02", "V1", "M1", 120000, "UPI",  "VIP task unlock"),
    ("T003", "2026-09-02 09:41", "V1", "M2", 216500, "IMPS", "Task commission clearance"),
    ("T004", "2026-09-02 15:27", "V1", "M1", 100000, "UPI",  "Withdrawal tax"),
    ("T005", "2026-09-08 13:05", "V2", "M3", 35000,  "UPI",  "Processing fee"),
    ("T006", "2026-09-09 10:30", "V2", "M3", 72000,  "UPI",  "Insurance charge"),
    ("T007", "2026-09-10 17:48", "V2", "M4", 85000,  "IMPS", "Clearance charge"),
    ("T008", "2026-09-14 11:20", "V3", "M5", 150000, "UPI",  "Account activation"),
    ("T009", "2026-09-15 12:10", "V3", "M5", 275000, "IMPS", "IPO allotment margin"),
    ("T010", "2026-09-16 16:45", "V3", "M6", 300000, "NEFT", "Profit withdrawal tax"),
]
BANK_2 = [  # mule -> intermediate -> master -> off-ramp
    ("T011", "2026-09-02 18:10", "M1", "I1", 170000, "IMPS", "Inv 4471 settlement"),
    ("T012", "2026-09-03 08:55", "M1", "I1", 80000,  "IMPS", "Inv 4472 settlement"),
    ("T013", "2026-09-02 19:30", "M2", "I1", 150000, "IMPS", "Inv 4473 settlement"),
    ("T014", "2026-09-03 09:20", "M2", "I2", 60000,  "UPI",  "Service charges"),
    ("T015", "2026-09-10 12:00", "M3", "I2", 90000,  "IMPS", "Service charges"),
    ("T016", "2026-09-11 08:40", "M4", "I2", 80000,  "IMPS", "Service charges"),
    ("T017", "2026-09-16 10:05", "M5", "I3", 200000, "IMPS", "Consulting fee"),
    ("T018", "2026-09-16 10:50", "M5", "I3", 192000, "IMPS", "Consulting fee"),
    ("T019", "2026-09-17 09:15", "M6", "I3", 275000, "NEFT", "Consulting fee"),
    ("T020", "2026-09-03 14:30", "I1", "MASTER", 360000, "NEFT", "Trade settlement"),
    ("T021", "2026-09-11 15:10", "I2", "MASTER", 212000, "NEFT", "Trade settlement"),
    ("T022", "2026-09-17 13:25", "I3", "MASTER", 640000, "NEFT", "Trade settlement"),
    ("T023", "2026-09-18 11:45", "MASTER", "EXCH", 500000, "NEFT", "Crypto off-ramp (external sink)"),
]

ALL_TXN = sorted(BANK_1 + BANK_2, key=lambda r: r[1])

# ---- running balances (opening balance of every mule/intermediate/master/exch = 0)
bal = {k: 0 for k in ACC if k not in VICTIMS}
snap = {}
for tid, t, a, b, amt, ch, rem in ALL_TXN:
    if a not in VICTIMS:
        bal[a] -= amt
        assert bal[a] >= 0, f"{tid}: {a} overdrawn"
    bal[b] += amt
    snap[tid] = (bal.get(a) if a not in VICTIMS else "", bal[b])
FINAL = dict(bal)


def bank_rows(txns):
    rows = []
    for i, (tid, t, a, b, amt, ch, rem) in enumerate(txns, 1):
        utr = f"UTR{ts(t):%y%m%d%H%M}{int(tid[1:]):03d}"
        rows.append([
            tid, f"{t}:00", ACC[a][0], ACC[a][1], ACC[a][2],
            ACC[b][0], ACC[b][1], ACC[b][2], amt, ch, utr, rem,
            snap[tid][0], snap[tid][1],
        ])
    return rows


UTR = {r[0]: r[10] for r in bank_rows(ALL_TXN)}
BANK_HEADER = ["txn_id", "timestamp", "from_account", "from_name", "from_bank",
               "to_account", "to_name", "to_bank", "amount_inr", "channel", "utr_ref",
               "remarks", "from_balance_after_inr", "to_balance_after_inr"]


def write_csv(name, header, rows):
    with open(os.path.join(OUT, name), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


write_csv("Bank_Logs_1.csv", BANK_HEADER, bank_rows(sorted(BANK_1, key=lambda r: r[1])))
write_csv("Bank_Logs_2.csv", BANK_HEADER, bank_rows(sorted(BANK_2, key=lambda r: r[1])))

# ---------------------------------------------------------------- CDRs
# (timestamp, caller, callee, duration_sec, type)
CDR_1 = [
    ("2026-08-29 11:20", "PX", "V1", 142, "VOICE"),
    ("2026-08-30 19:40", "PX", "V1", 310, "VOICE"),
    ("2026-08-30 19:58", "PX", "V1", 0,   "SMS"),
    ("2026-09-01 09:55", "V1", "PX", 428, "VOICE"),
    ("2026-09-01 10:20", "PX", "M1", 95,  "VOICE"),
    ("2026-09-01 10:58", "V1", "PX", 205, "VOICE"),
    ("2026-09-01 11:10", "PX", "M1", 60,  "VOICE"),
    ("2026-09-02 09:30", "PX", "V1", 366, "VOICE"),
    ("2026-09-02 09:50", "PX", "M2", 88,  "VOICE"),
    ("2026-09-02 15:05", "PX", "V1", 512, "VOICE"),
    ("2026-09-02 18:00", "PX", "M1", 120, "VOICE"),
    ("2026-09-02 19:05", "PX", "M2", 75,  "VOICE"),
    ("2026-09-03 08:30", "PX", "M1", 52,  "VOICE"),
    ("2026-09-03 10:10", "V1", HELPLINE, 480, "VOICE"),
    ("2026-09-03 14:00", "PX", "PM", 233, "VOICE"),
    ("2026-09-05 14:10", "SIMB", "V2", 275, "VOICE"),
    ("2026-09-07 20:15", "SIMB", "V2", 340, "VOICE"),
    ("2026-09-08 12:40", "SIMB", "V2", 410, "VOICE"),
    ("2026-09-09 10:05", "V2", "SIMB", 198, "VOICE"),
    ("2026-09-09 15:00", "PX", "V2", 120, "VOICE"),
    ("2026-09-10 11:30", "SIMB", "M3", 75, "VOICE"),
    ("2026-09-10 17:20", "SIMB", "V2", 288, "VOICE"),
    ("2026-09-10 18:05", "SIMB", "M4", 66, "VOICE"),
    ("2026-09-11 08:15", "SIMB", "M4", 58, "VOICE"),
    ("2026-09-11 10:45", "V2", HELPLINE, 395, "VOICE"),
    ("2026-09-11 14:30", "SIMB", "PM", 190, "VOICE"),
    # unrelated noise
    ("2026-09-01 13:15", "N1", "N2", 64,  "VOICE"),
    ("2026-09-04 21:05", "N2", "N1", 310, "VOICE"),
    ("2026-09-09 08:45", "N1", "N3", 45,  "VOICE"),
]
CDR_2 = [
    ("2026-09-10 16:20", "SIMC", "V3", 190, "VOICE"),
    ("2026-09-12 11:05", "SIMC", "V3", 276, "VOICE"),
    ("2026-09-13 20:30", "V3", "PX", 240, "VOICE"),
    ("2026-09-14 11:00", "SIMC", "V3", 301, "VOICE"),
    ("2026-09-14 15:00", "SIMC", "M5", 48, "VOICE"),
    ("2026-09-15 11:40", "SIMC", "V3", 388, "VOICE"),
    ("2026-09-16 09:30", "SIMC", "M5", 64, "VOICE"),
    ("2026-09-16 10:30", "SIMC", "M5", 55, "VOICE"),
    ("2026-09-16 16:10", "SIMC", "V3", 245, "VOICE"),
    ("2026-09-17 08:50", "SIMC", "M6", 70, "VOICE"),
    ("2026-09-17 13:00", "SIMC", "PM", 205, "VOICE"),
    ("2026-09-18 11:20", "PX", "PM", 160, "VOICE"),
    ("2026-09-18 15:20", "PM", "PX", 94, "VOICE"),
    ("2026-09-19 10:40", "V3", HELPLINE, 420, "VOICE"),
    # unrelated noise
    ("2026-09-12 18:20", "N3", "N1", 58, "VOICE"),
    ("2026-09-15 09:10", "N2", "N3", 133, "VOICE"),
    ("2026-09-18 22:40", "N3", "N2", 27, "VOICE"),
]
CDR_HEADER = ["call_id", "timestamp", "caller_msisdn", "callee_msisdn", "duration_sec", "call_type",
              "caller_imei", "callee_imei", "caller_location", "callee_location"]


def msisdn(k):
    return HELPLINE if k == HELPLINE else "+91" + PH[k]


def cdr_rows(calls, prefix):
    rows = []
    for i, (t, a, b, dur, typ) in enumerate(sorted(calls, key=lambda r: r[0]), 1):
        rows.append([
            f"{prefix}{i:03d}", f"{t}:00", msisdn(a), msisdn(b), dur, typ,
            IMEI[a] if a in IMEI else "", IMEI[b] if b in IMEI else "",
            LOC[a] if a in LOC else "", LOC[b] if b in LOC else "NCRP Helpline",
        ])
    return rows


write_csv("CDR_Logs_1.csv", CDR_HEADER, cdr_rows(CDR_1, "C1-"))
write_csv("CDR_Logs_2.csv", CDR_HEADER, cdr_rows(CDR_2, "C2-"))

# ---------------------------------------------------------------- FIR texts
def fmt_ph_spaced(k):   # +91 99999 00101
    p = PH[k]
    return f"+91 {p[:5]} {p[5:]}"


def fmt_ph_dash(k):     # +91-99999-00101
    p = PH[k]
    return f"+91-{p[:5]}-{p[5:]}"


tot1 = sum(r[4] for r in BANK_1 if r[2] == "V1")
tot2 = sum(r[4] for r in BANK_1 if r[2] == "V2")
tot3 = sum(r[4] for r in BANK_1 if r[2] == "V3")
assert (tot1, tot2, tot3) == (486500, 192000, 725000)
tx = {r[0]: r for r in BANK_1}


def line_en(tid):
    r = tx[tid]
    d = ts(r[1])
    return (f"  {d:%d-%m-%Y %H:%M} | Rs. {inr(r[4])} | {r[5]} | to A/c {ACC[r[3]][0]} "
            f"({ACC[r[3]][1]}, {ACC[r[3]][2]}) | Ref {UTR[tid]}")


def line_hi(tid):
    r = tx[tid]
    d = ts(r[1])
    return (f"  {d:%d-%m-%Y %H:%M} | ₹{inr(r[4])} | {r[5]} | खाता {ACC[r[3]][0]} "
            f"({ACC[r[3]][1]}, {ACC[r[3]][2]}) | संदर्भ {UTR[tid]}")


FIR1 = f"""[SYNTHETIC TEST DATA - FICTIONAL CASE FOR HACKATHON DEMO ONLY]

FIRST INFORMATION REPORT (Under Section 173 BNSS)

FIR No.            : 0142/2026
Police Station     : Cyber Crime Police Station, Bengaluru East Division, Karnataka
Date of Complaint  : 03-09-2026
Date of FIR        : 03-09-2026
Sections           : BNS 318(4), BNS 319(2); IT Act 66C, 66D

1. COMPLAINANT
Name               : Rohan Deshpande, age 29, software tester
Mobile             : {fmt_ph_spaced('V1')}
Address            : Flat 4B, Lakeview Residency, Indiranagar, Bengaluru - 560038
Bank Account       : {ACC['V1'][0]} ({ACC['V1'][2]}, Indiranagar branch)

2. ACCUSED (as known at the time of complaint)
Name               : Vikrant Malhotra, alias "Vicky", age and address unknown
Contact Number     : {fmt_ph_spaced('PX')} (calls, SMS and Telegram)
Telegram Handle    : @PrimeTasksHub_Official

3. BRIEF FACTS
On 28-08-2026 the complainant received a message on Telegram from the handle
@PrimeTasksHub_Official offering part-time work: liking and rating online videos for
a commission. After small initial payouts of Rs. 1,000 and Rs. 1,500, he was added to
a "VIP task group" and told that higher-value prepaid tasks would return 30 to 40 percent
profit. The person introducing himself as "Vicky" (number {fmt_ph_spaced('PX')}) called the
complainant repeatedly between 29-08-2026 and 02-09-2026 and instructed him to deposit
money to unlock each task level. When the complainant asked to withdraw his balance he
was asked to pay a "withdrawal tax". After the fourth payment the group was deleted and
the number stopped responding.

4. TRANSACTIONS REPORTED
Total amount reported lost: Rs. {inr(tot1)}
{line_en('T001')}
{line_en('T002')}
{line_en('T003')}
{line_en('T004')}

5. EVIDENCE REFERENCES
EV-1A : Telegram chat screenshots (14 images) with handle @PrimeTasksHub_Official
EV-1B : Bank statement of A/c {ACC['V1'][0]}, 01-09-2026 to 03-09-2026
EV-1C : UPI/IMPS payment receipts for the four transactions listed above
EV-1D : Call log screenshot showing number {fmt_ph_spaced('PX')}
EV-1E : Complaint filed on National Cyber Crime Reporting Portal after calling 1930

6. SUPPLEMENTARY INVESTIGATION NOTE (dated 06-09-2026, Investigating Officer)
Beneficiary bank statements obtained. Funds in A/c {ACC['M1'][0]} and A/c {ACC['M2'][0]}
were moved onward within 24 hours to A/c {ACC['I1'][0]} ({ACC['I1'][1]}) and then
consolidated into A/c {ACC['MASTER'][0]} ({ACC['MASTER'][1]}). Preliminary CDR analysis
shows that the number {fmt_ph_spaced('PX')} was operated from handset IMEI {IMEI_X}.
Tower data places the handset in Jaipur, Rajasthan. Request made to the Jaipur
commissionerate for subscriber details. Matter is under investigation.

Investigating Officer : Inspector R. Hegde (fictional)
"""

FIR2 = f"""[सिंथेटिक परीक्षण डेटा - केवल हैकथॉन डेमो हेतु काल्पनिक प्रकरण]

प्रथम सूचना रिपोर्ट (धारा 173 बीएनएसएस)

एफआईआर संख्या        : 0087/2026
थाना                  : साइबर क्राइम थाना, गौतमबुद्ध नगर (नोएडा), उत्तर प्रदेश
शिकायत की तिथि       : 11-09-2026
एफआईआर पंजीकरण तिथि  : 11-09-2026
धाराएं                : बीएनएस 318(4), 319(2), 308; आईटी एक्ट 66सी, 66डी

1. शिकायतकर्ता
नाम                   : सुनीता वर्मा, आयु 34 वर्ष, गृहिणी
मोबाइल                : {PH['V2']}
पता                   : फ्लैट 202, शिवालिक अपार्टमेंट, सेक्टर 62, नोएडा - 201309
बैंक खाता             : {ACC['V2'][0]} ({ACC['V2'][2]}, सेक्टर 62 शाखा)

2. अभियुक्त
नाम                   : विक्रांत मल्होत्रा उर्फ़ "विक्की" (स्वयं को "रिकवरी मैनेजर" बताता है)
संपर्क नंबर           : {PH['SIMB']} (कॉल) तथा {PH['PX']} (व्हाट्सऐप)
ऐप का नाम            : "रुपीफ्लैश कैश" लोन ऐप

3. घटना का संक्षिप्त विवरण
शिकायतकर्ता ने दिनांक 05-09-2026 को अपने मोबाइल में "रुपीफ्लैश कैश" नामक लोन ऐप डाउनलोड
किया और ₹8,000 के छोटे ऋण के लिए आवेदन किया। ऐप के संचालकों ने ऋण स्वीकृत करने के नाम पर
प्रोसेसिंग शुल्क, बीमा शुल्क और "क्लीयरेंस चार्ज" की मांग की। इसके बाद स्वयं को "विक्की" बताने
वाले व्यक्ति ने नंबर {PH['SIMB']} से बार-बार फोन करके धमकी दी कि यदि भुगतान नहीं किया गया तो
शिकायतकर्ता की तस्वीरें एडिट करके उसके सभी संपर्कों को भेज दी जाएंगी। वही व्यक्ति व्हाट्सऐप
पर नंबर {PH['PX']} से भी संपर्क कर रहा था और स्वयं को "विक्की मल्होत्रा" बता रहा था। डर के
कारण शिकायतकर्ता ने नीचे दिए गए खातों में रकम जमा की। ऋण की कोई राशि प्राप्त नहीं हुई।

4. रिपोर्ट किए गए लेन-देन
कुल ठगी की राशि: ₹{inr(tot2)}
{line_hi('T005')}
{line_hi('T006')}
{line_hi('T007')}

5. साक्ष्य संदर्भ
EV-2A : "रुपीफ्लैश कैश" ऐप के स्क्रीनशॉट (9 चित्र)
EV-2B : व्हाट्सऐप चैट का स्क्रीनशॉट, नंबर {PH['PX']}
EV-2C : खाता {ACC['V2'][0]} का बैंक विवरण, 05-09-2026 से 11-09-2026
EV-2D : तीनों भुगतानों की रसीदें
EV-2E : 1930 पर कॉल करने के बाद राष्ट्रीय साइबर अपराध पोर्टल पर दर्ज शिकायत

6. पूरक जांच टिप्पणी (दिनांक 13-09-2026, विवेचक)
बैंक विवरण से ज्ञात हुआ कि खाता {ACC['M3'][0]} और खाता {ACC['M4'][0]} से रकम आगे खाता
{ACC['I2'][0]} ({ACC['I2'][1]}) में भेजी गई और वहाँ से खाता {ACC['MASTER'][0]}
({ACC['MASTER'][1]}) में जमा हुई। कॉल डिटेल रिकॉर्ड (CDR) के प्रारंभिक विश्लेषण में पाया गया कि
नंबर {PH['SIMB']} और नंबर {PH['PX']} दोनों एक ही मोबाइल हैंडसेट (IMEI {IMEI_X}) में
प्रयुक्त हुए हैं। हैंडसेट की लोकेशन जयपुर (राजस्थान) क्षेत्र में पाई गई। मामले की विवेचना जारी है।

विवेचक : उप-निरीक्षक एस. त्यागी (काल्पनिक)
"""

FIR3 = f"""[SYNTHETIC TEST DATA - FICTIONAL CASE FOR HACKATHON DEMO ONLY]

FIRST INFORMATION REPORT (Under Section 173 BNSS)

FIR No.            : 0311/2026
Police Station     : Cyber Police Station, Pune City, Maharashtra
Date of Complaint  : 19-09-2026
Date of FIR        : 19-09-2026
Sections           : BNS 318(4), BNS 319(2); IT Act 66C, 66D

1. COMPLAINANT
Name               : Meera Kulkarni, age 41, school teacher
Mobile             : {fmt_ph_dash('V3')}
Address            : B-12, Shanti Nagar Society, Kothrud, Pune - 411038
Bank Account       : {ACC['V3'][0]} ({ACC['V3'][2]}, Kothrud branch)

2. ACCUSED (as known at the time of complaint)
Name               : "V. Malhotra" / "Vicky M." (as signed on the fake portal's support page)
Contact Numbers    : {fmt_ph_dash('SIMC')} (caller), {fmt_ph_dash('PX')} (listed as "customer support")
Platform           : "AlphaBull Prime" online trading portal and WhatsApp group "Wealth Builders Circle"

3. BRIEF FACTS
In the first week of September 2026 the complainant was added to the WhatsApp group
"Wealth Builders Circle", which promoted guaranteed returns through the "AlphaBull Prime"
trading portal. A person calling from {fmt_ph_dash('SIMC')} introduced himself as a "senior
analyst" and guided her to open an account on the portal, which displayed fabricated profits.
When she had doubts on 13-09-2026 she called the "customer support" number {fmt_ph_dash('PX')}
shown on the portal and was reassured by the same voice. She then transferred funds for
"account activation", "IPO allotment margin" and finally a "profit withdrawal tax". When she
asked for withdrawal the portal became inaccessible and calls were not answered.

4. TRANSACTIONS REPORTED
Total amount reported lost: Rs {inr(tot3)}
{line_en('T008')}
{line_en('T009')}
{line_en('T010')}

5. EVIDENCE REFERENCES
EV-3A : Screenshots of the "AlphaBull Prime" portal dashboard and support page
EV-3B : WhatsApp group chat export "Wealth Builders Circle"
EV-3C : Bank statement of A/c {ACC['V3'][0]}, 01-09-2026 to 19-09-2026
EV-3D : Payment receipts for the three transactions listed above
EV-3E : Complaint registered on cybercrime portal after calling 1930

6. SUPPLEMENTARY INVESTIGATION NOTE (dated 21-09-2026, Investigating Officer)
Preliminary CDR analysis shows that the calling number {fmt_ph_dash('SIMC')} and the "support"
number {fmt_ph_dash('PX')} were both operated from handset IMEI {IMEI_X}, located in
Jaipur, Rajasthan. Funds in A/c {ACC['M5'][0]} and A/c {ACC['M6'][0]} were moved to
A/c {ACC['I3'][0]} ({ACC['I3'][1]}) and consolidated into A/c {ACC['MASTER'][0]}
({ACC['MASTER'][1]}), from which Rs. 5,00,000 was transferred on 18-09-2026 to an
external crypto exchange omnibus account. Matter is under investigation.

Investigating Officer : Sub-Inspector A. Jadhav (fictional)
"""

for name, text in (("FIR_1_English.txt", FIR1), ("FIR_2_Hindi.txt", FIR2), ("FIR_3_English.txt", FIR3)):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        f.write(text)

print("Written to", OUT)
print("PLANTED shared phone :", "+91" + PH["PX"])
print("PLANTED shared IMEI  :", IMEI_X)
print("Final balances (freeze ranking):")
for k, v in sorted(FINAL.items(), key=lambda kv: -kv[1]):
    print(f"  {ACC[k][0]}  {ACC[k][1]:<36} Rs {v:>9,}")