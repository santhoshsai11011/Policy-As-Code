from pathlib import Path
import pdfplumber

BASE = Path(__file__).resolve().parent
PDF = BASE / "input" / "AI Training Data PII Policy.pdf"
OUTPUT = BASE / "output" / "policy_text.txt"

def extract_policy_text():
    with pdfplumber.open(PDF) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]

    text = "\n\n".join(
        f"--- PAGE {i + 1} ---\n{page}"
        for i, page in enumerate(pages)
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(text, encoding="utf-8")

    print(f"Extracted {len(pages)} pages")
    print(f"Saved to: {OUTPUT}")

if __name__ == "__main__":
    extract_policy_text()