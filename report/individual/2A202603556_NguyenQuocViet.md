# Báo cáo cá nhân — Day 6

## Dữ liệu và pipeline

- **Corpus:** NIST SP 800-61r3 (2025), *Incident Response Recommendations and Considerations for Cybersecurity Risk Management*. Tài liệu nêu tổ chức phi chính phủ có thể sử dụng tự nguyện và tài liệu không thuộc bản quyền tại Hoa Kỳ; manifest lưu trích dẫn nguồn.
- **Quy tắc tính:** 35 trang PDF có ít nhất 1.500 ký tự trích xuất; bỏ bìa/front matter, trang tài liệu tham khảo 44–45 và trang ngắn. Mỗi dòng dữ liệu giữ số trang PDF vật lý, URL nguồn, chapter/section và revision.
- **Trích xuất:** pypdf 6.11.0; giữ dòng văn bản, chưa OCR; bảng được trích dạng text nên có thể mất bố cục cột.
- **Embedding:** `sentence-transformers/all-MiniLM-L6-v2`, 384 chiều, chạy local; sentence-transformers 5.6.1. Chi phí API $0; chưa tính điện năng.
- **Vector store:** Chroma PersistentClient 1.5.9, cosine distance, lưu tại `starter/results/chroma/` (database không commit).
- **Metadata:** document ID, URL nguồn, trang PDF, chapter, section, revision và năm xuất bản. Filter dùng `chapter` do câu hỏi cung cấp.

## Cấu hình và benchmark

- **A:** chia kích thước cố định 500 ký tự, overlap 50.
- **B:** gom dòng/đoạn PDF theo cấu trúc đến 500 ký tự.
- **C:** như B, thêm filter chapter nếu câu hỏi nêu phạm vi. B–C chỉ khác filter.
- Bộ benchmark có 20 câu tiếng Việt; runner dùng bản dịch tiếng Anh nội bộ để truy xuất trên corpus/model tiếng Anh. Evidence quote được giữ nguyên tiếng Anh và kiểm tra trong trang nguồn. Có 15 dev, 5 test và 6 câu có filter (4 dev, 2 test). Split được cố định trước khi chạy; chọn cấu hình bằng dev theo thứ tự Evidence Hit@3, grounding, tài nguyên.
- **Lệnh chạy:** từ `starter/`, chạy `python scripts/prepare_nist_corpus.py`, sau đó `python -m src.run`. Model chạy offline từ cache, vector store Chroma; không cần API key hoặc Docker.

## Kết quả truy xuất

| Chiến lược | Split | Hit@1 | Evidence Hit@3 | Số chunk | Thời gian nạp | Chi phí API |
|---|---|---:|---:|---:|---:|---:|
| A | dev | 2/15 | 5/15 | 209 | 3.120 giây | $0 |
| A | test | 0/5 | 1/5 | 209 | 3.120 giây | $0 |
| B | dev | 5/15 | 6/15 | 202 | 2.145 giây | $0 |
| B | test | 0/5 | 1/5 | 202 | 2.145 giây | $0 |
| C | dev | 5/15 | 7/15 | 202 | 2.625 giây | $0 |
| C | test | 0/5 | 1/5 | 202 | 2.625 giây | $0 |

Tổng thời gian nạp ba chiến lược là 37.011 giây: khởi động/schema vector store 25.778 giây, embedding 8.681 giây, ghi vector 2.508 giây, chia đoạn 0.044 giây. Truy vấn embedding, truy xuất và đánh giá mất 1.076 giây. Thời gian từng chiến lược gồm chia đoạn, embedding và ghi vector; không tính thời gian nạp model. Đây là một lần chạy local.

## Đánh giá thủ công

Nhãn dưới đây do **Codex đánh giá có AI hỗ trợ, một người chấm duy nhất**; không phải đánh giá độc lập. Học viên đã xem xét và chấp nhận nhãn. Lý do chi tiết nằm trong `starter/results/coherence_audit.csv`, `metadata_audit.csv` và `grounding_audit.csv`.

| Chiến lược | Coherence /2 (n=10) | Metadata đúng/đủ (test top-3) | Filter test tuân thủ | Grounding 0/1/2 (n=5), TB /2 |
|---|---:|---:|---:|---|
| A | 0/9/1; **1.1** | 15/15 | N/A | 2/2/1; **0.8** |
| B | 0/7/3; **1.3** | 15/15 | N/A | 2/1/2; **1.0** |
| C | 0/7/3; **1.3** | 15/15 | 6/6 | 2/1/2; **1.0** |

Coherence dùng cùng 10 vị trí nguồn, trang PDF 9–18, chấm chunk đầu tiên tại mỗi vị trí. Metadata bắt buộc (`document_id`, source, page, chapter) có mặt và đúng trong cả 45 bản ghi test top-3. Hai câu test có filter trả về đúng chapter trong cả 6 kết quả C. A và B không áp dụng filter.

## Phân tích và kết luận

- A→B tăng Hit@1 dev thêm 3 và Evidence Hit@3 thêm 1, trong khi giảm 7 chunk; Evidence Hit@3 test vẫn 1/5.
- B→C tăng Evidence Hit@3 dev thêm 1, không đổi số chunk; test không cải thiện. Filter theo chapter quá rộng với câu hỏi nhắm đến một subsection cụ thể.
- Chọn C theo tiêu chí dev đã định trước (Evidence Hit@3 = 7/15). Test nhỏ chưa cho thấy khả năng khái quát; cả ba cấu hình chỉ truy xuất đúng evidence cho 1/5 câu test.
- **Ví dụ lỗi:** q16 (hướng dẫn danh mục tài sản, trang 24) bị cả ba cấu hình bỏ sót; top kết quả nghiêng về phần tóm tắt. q20 (hướng dẫn phân tích sự cố, trang 36) cũng bị bỏ sót; filter chapter 3 của C vẫn trả về trang mở đầu chương thay vì subsection phân tích sự cố. q19 trả về phần lớn đoạn giám sát mạng đúng nhưng chunk đầu bị cắt đầu danh sách, thiếu mục mạng có dây/không dây.
- **Giới hạn:** chỉ một tài liệu NIST, năm câu test, một lần chạy local, một người chấm, trích xuất PDF dạng text và filter chapter còn rộng. Đây là metric truy xuất evidence, không phải độ chính xác câu trả lời của LLM.
- Split test được báo cáo sau khi cấu hình đã cố định và không được dùng để thay đổi chunking, filter hay model.

Artifacts: `starter/data/manifest.json`, `starter/data/pages.jsonl`, `starter/benchmark/questions.jsonl`, `starter/results/metrics.json`, `starter/results/retrieval_traces.json`, `starter/results/run_metadata.json` và ba file audit trong `starter/results/`.
