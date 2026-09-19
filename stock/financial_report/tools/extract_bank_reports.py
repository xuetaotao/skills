import re
import sys
from pathlib import Path

from pypdf import PdfReader


def extract_text(path: Path) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)


def first_context(text: str, term: str, width: int = 180) -> str:
    match = re.search(term, text)
    if not match:
        return "NOT FOUND"
    start = max(0, match.start() - 30)
    end = min(len(text), match.end() + width)
    return re.sub(r"\s+", " ", text[start:end]).strip()


artifact_dir = Path(sys.argv[1])
ping_an = Path(sys.argv[2])
terms = [
    r"营业收入",
    r"归属于(?:本行|母公司|公司)(?:普通股)?股东的净利润",
    r"资产总额|总资产",
    r"不良贷款率",
    r"拨备覆盖率",
    r"净利息收益率|净息差|净利差",
    r"operating income|total operating income",
    r"profit attributable to (?:equity )?shareholders|profit attributable to owners",
    r"total assets",
    r"non-performing loan ratio",
    r"allowance coverage ratio|provision coverage ratio",
    r"net interest margin|net interest spread",
    r"operating income (?:was|of)",
    r"net profit attributable",
    r"profit attributable to shareholders of the Bank",
    r"RMB13,?952|13,?952 million",
    r"RMB4,?151|4,?151 million",
    r"HKD|Hong Kong dollars?",
    r"presented in RMB|denominated in RMB|RMB million",
]

paths = sorted(artifact_dir.glob("*-2026h1-summary.pdf")) + [ping_an]
for path in paths:
    text = extract_text(path)
    print(f"\n===== {path.stem} pages={len(PdfReader(path).pages)} =====")
    for term in terms:
        print(f"[{term}] {first_context(text, term)}")