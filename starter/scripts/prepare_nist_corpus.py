"""Download and page-segment NIST SP 800-61r3 for the lab corpus."""
import json
import re
import time
from pathlib import Path
from urllib.request import Request, urlopen

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
URL = "https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-61r3.pdf"
PDF_PATH = ROOT / "data" / "NIST.SP.800-61r3.pdf"


def normalize_for_match(value: str) -> str:
    return " ".join(re.findall(r"[\w]+", value.casefold()))


def main():
    data_dir = ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    if not PDF_PATH.exists():
        request = Request(URL, headers={"User-Agent": "Day06 academic lab corpus/1.0"})
        with urlopen(request, timeout=60) as response:
            PDF_PATH.write_bytes(response.read())

    reader = PdfReader(str(PDF_PATH))
    pages = []
    for physical_page, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        # Exclude front matter and the references pages rather than counting dense metadata as content.
        if physical_page <= 8 or physical_page in {44, 45}:
            continue
        # Page ranges follow the publication's printed table of contents (PDF pp. 9-48).
        # This avoids mistaking running page numbers and CSF control IDs for headings.
        if physical_page <= 8:
            current_chapter, current_section = "front-matter", "front-matter"
        elif physical_page == 9:
            current_chapter, current_section = "1", "executive-summary"
        elif physical_page <= 11:
            current_chapter, current_section = "1", "1"
        elif physical_page == 12:
            current_chapter, current_section = "2", "2"
        elif physical_page == 13:
            current_chapter, current_section = "2", "2.1"
        elif physical_page <= 15:
            current_chapter, current_section = "2", "2.2"
        elif physical_page <= 17:
            current_chapter, current_section = "2", "2.3"
        elif physical_page == 18:
            current_chapter, current_section = "3", "3"
        elif physical_page <= 30:
            current_chapter, current_section = "3", "3.1"
        elif physical_page <= 43:
            current_chapter, current_section = "3", "3.2"
        else:
            current_chapter, current_section = "appendix", "appendix"
        cleaned = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        if len(cleaned) < 1500:
            continue
        pages.append({"document_id": "nist-sp-800-61r3", "source": URL,
                      "page": physical_page, "text": cleaned,
                      "metadata": {"chapter": current_chapter, "section": current_section,
                                   "revision": "3", "published_year": 2025}})

    if len(pages) < 30:
        raise SystemExit(f"Only {len(pages)} pages have at least 1,500 extracted characters; corpus minimum is 30.")
    (data_dir / "pages.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in pages), encoding="utf-8")
    manifest = {
        "source_id": "nist-sp-800-61r3",
        "title": "Incident Response Recommendations and Considerations for Cybersecurity Risk Management: A CSF 2.0 Community Profile",
        "authors": ["Alex Nelson", "Sanjay Rekhi", "Murugiah Souppaya", "Karen Scarfone"],
        "publisher": "National Institute of Standards and Technology, U.S. Department of Commerce",
        "source_path_or_url": URL,
        "doi": "10.6028/NIST.SP.800-61r3",
        "license_or_permission": "NIST SP 800-61r3 nêu rằng tổ chức phi chính phủ có thể sử dụng tự nguyện và tài liệu không thuộc bản quyền tại Hoa Kỳ; NIST khuyến khích trích dẫn nguồn. Cần kiểm tra riêng quyền của tài liệu bên thứ ba; bản trích xuất này không gồm hình ảnh.",
        "attribution": "Nelson, A., Rekhi, S., Souppaya, M., & Scarfone, K. (2025). NIST SP 800-61r3. https://doi.org/10.6028/NIST.SP.800-61r3",
        "accessed_at": time.strftime("%Y-%m-%d", time.gmtime()),
        "content_unit_rule": "Một trang PDF vật lý có nội dung, ít nhất 1.500 ký tự sau khi bỏ dòng trống; loại bìa/front matter, references (trang PDF vật lý 44-45) và trang ngắn. page là số trang PDF vật lý; giữ phần bảng thuật ngữ.",
        "pages_counted": len(pages),
        "pdf_physical_pages": len(reader.pages),
        "excluded_short_pages": len(reader.pages) - len(pages),
        "copyright_note": "Tại trang in số 2, tài liệu nêu tổ chức phi chính phủ có thể sử dụng tự nguyện và tài liệu không thuộc bản quyền tại Hoa Kỳ.",
    }
    (data_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    questions_path = ROOT / "benchmark" / "questions.jsonl"
    if questions_path.exists():
        questions = [json.loads(line) for line in questions_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        for question in questions:
            quote = normalize_for_match(question["evidence_quote"])
            matches = [row["page"] for row in pages if quote in normalize_for_match(row["text"])]
            if not matches:
                raise SystemExit(f"Evidence not found in extracted corpus for {question['id']}: {question['evidence_quote']}")
            question["gold_source_id"] = "nist-sp-800-61r3"
            question["gold_page"] = matches[0]
        questions_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in questions), encoding="utf-8")
    print(f"Prepared {len(pages)} content pages from {len(reader.pages)} physical PDF pages.")


if __name__ == "__main__":
    main()
