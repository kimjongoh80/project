"""IEEE OUI 레지스트리(oui.csv, mam.csv, oui36.csv)를 앱용 압축 테이블(data/oui.tsv.gz)로 변환한다.

원본: https://standards-oui.ieee.org/oui/oui.csv  (선택: oui28/mam.csv, oui36/oui36.csv)
사용: python tools/build_oui.py <csv 파일> [<csv 파일> ...]
"""
import csv
import gzip
import os
import re
import sys

SUFFIX = re.compile(
    r"[\s,.]*(co\.?,?\s*ltd|company limited|co\.?\s*limited|limited|ltd|inc|incorporated|corporation|corp"
    r"|gmbh|s\.?a\.?|llc|l\.?l\.?c|ag|b\.?v|oy|ab|plc|pte|pvt|technologies|technology|tech)\.?$",
    re.I)


def clean(name):
    name = " ".join(name.split())
    for _ in range(3):
        new = SUFFIX.sub("", name).strip(" ,.")
        if new == name or not new:
            break
        name = new
    return name


def main(paths):
    rows = {}
    for p in paths:
        with open(p, encoding="utf-8", errors="replace", newline="") as f:
            for r in csv.DictReader(f):
                a = r.get("Assignment", "").strip().upper()
                n = clean(r.get("Organization Name", ""))
                if a and n and n.lower() != "private":
                    rows[a] = n
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "oui.tsv.gz")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with gzip.open(out, "wt", encoding="utf-8") as f:
        for a in sorted(rows):
            f.write(f"{a}\t{rows[a]}\n")
    print(f"{len(rows)} entries -> {out} ({os.path.getsize(out) // 1024} KB)")


if __name__ == "__main__":
    main(sys.argv[1:])
