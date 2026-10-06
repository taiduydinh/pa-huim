import json
import os
import smtplib
import time
from pathlib import Path
from email.message import EmailMessage
from datetime import datetime, timezone

ROOT = Path("/work/first8_batch")
RESULTS = ROOT / "results"
MARKER = ROOT / "email_sent.marker"

CASES = [
    "hui_chainstore_T7",
    "up_chainstore_T4",
    "fhm_accidents_80",
    "hui_chainstore_80",
    "up_chainstore_100",
    "hui_accidents_T1",
    "hui_ecommerce_T4",
    "hui_ecommerce_60",
]

EMAIL = os.environ["PAHUIM_EMAIL"]
PASSWORD = os.environ["PAHUIM_GMAIL_APP_PASSWORD"]


def fmt_runtime(ms):
    try:
        sec = float(ms) / 1000.0

        if sec >= 3600:
            return f"{sec/3600:.2f} h"

        if sec >= 60:
            return f"{sec/60:.2f} min"

        return f"{sec:.2f} s"

    except Exception:
        return str(ms)


def send_email(rows):
    ok = sum(r["status"] == "ok" for r in rows)
    timeout = sum(r["status"] == "timeout" for r in rows)
    error = len(rows) - ok - timeout

    subject = (
        f"PA-HUIM: First 8 experiments completed "
        f"({ok} OK, {timeout} timeout, {error} error)"
    )

    lines = [
        "The first 8 PA-HUIM baseline experiments have completed.",
        "",
        f"OK: {ok}",
        f"Timeout: {timeout}",
        f"Error: {error}",
        "",
        "Results:",
        "",
    ]

    for i, r in enumerate(rows, 1):
        lines += [
            f"{i}. {r['case_id']}",
            f"   Algorithm: {r['algorithm']}",
            f"   Dataset: {r['dataset']}",
            f"   Status: {r['status']}",
            f"   Runtime: {fmt_runtime(r['runtime_ms'])}",
            f"   Peak memory: {r['peak_memory_mb']} MB",
            f"   Patterns: {r['pattern_count']}",
            "",
        ]

    lines += [
        f"Notification generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "Results directory:",
        "/work/first8_batch/results",
    ]

    msg = EmailMessage()

    msg["From"] = EMAIL
    msg["To"] = EMAIL
    msg["Subject"] = subject

    msg.set_content("\n".join(lines))

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(EMAIL, PASSWORD)
        smtp.send_message(msg)


print(
    datetime.now(timezone.utc).isoformat(),
    "first-8 email monitor started",
    flush=True,
)

while True:

    if MARKER.exists():
        print("Email already sent; exiting.", flush=True)
        break

    files = [RESULTS / f"{x}.json" for x in CASES]

    if all(f.exists() for f in files):

        rows = []

        for case, f in zip(CASES, files):

            x = json.loads(f.read_text())
            r = x.get("result", {})

            rows.append({
                "case_id": case,
                "algorithm": x.get("algorithm", ""),
                "dataset": x.get("dataset", ""),
                "status": r.get("status", "?"),
                "runtime_ms": r.get("runtime_ms", ""),
                "peak_memory_mb": r.get("peak_memory_mb", ""),
                "pattern_count": r.get("pattern_count", ""),
            })

        try:
            send_email(rows)

            MARKER.write_text(
                datetime.now(timezone.utc).isoformat(),
                encoding="utf-8",
            )

            print(
                datetime.now(timezone.utc).isoformat(),
                "FINAL EMAIL SENT SUCCESSFULLY",
                flush=True,
            )

            break

        except Exception as e:
            print(
                datetime.now(timezone.utc).isoformat(),
                "EMAIL ERROR:",
                repr(e),
                "Retrying in 5 minutes.",
                flush=True,
            )

            time.sleep(300)
            continue

    completed = sum(f.exists() for f in files)

    print(
        datetime.now(timezone.utc).isoformat(),
        f"completed={completed}/8",
        flush=True,
    )

    time.sleep(60)
