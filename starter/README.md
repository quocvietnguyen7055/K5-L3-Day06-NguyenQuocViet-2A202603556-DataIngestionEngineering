# Pipeline nạp dữ liệu — Day 06

Pipeline hỗ trợ PostgreSQL + pgvector hoặc Chroma lưu bền vững tại máy:

- **A:** cửa sổ cố định 500 ký tự, chồng lấn 50 ký tự.
- **B:** gom các dòng/đoạn PDF theo cấu trúc, tối đa 500 ký tự.
- **C:** dùng cùng cách chia như B; chỉ áp dụng filter metadata khi câu hỏi nêu phạm vi.

Cả ba chiến lược dùng cùng corpus, benchmark, model embedding thật và cosine distance. Lỗi từ model/provider sẽ dừng pipeline; không có vector giả.

## Cài đặt và chạy

Từ thư mục `starter/`, tạo môi trường Python 3.11+, cài thư viện và sao chép `.env.example` thành `.env`. Cấu hình mẫu dùng model `sentence-transformers/all-MiniLM-L6-v2` và Chroma lưu cục bộ, không cần API key hoặc Docker. Nếu model chưa có trong bộ nhớ đệm, cần tải model một lần.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python scripts/prepare_nist_corpus.py
python -m src.run
```

Để dùng API embedding, đặt `EMBEDDING_PROVIDER=api`, tên model, endpoint và khóa API trong `.env`. Để dùng PostgreSQL, đặt `VECTOR_STORE=pgvector`, cấu hình `DATABASE_URL` và khởi động database bằng Docker Compose. `python scripts/check_setup.py` chỉ kiểm tra kết nối PostgreSQL, không chạy benchmark. Không commit `.env`.

## Corpus và quyền sử dụng

Corpus là NIST SP 800-61r3, tải từ trang ấn phẩm chính thức của NIST bằng `scripts/prepare_nist_corpus.py`. Tài liệu nêu rằng tổ chức phi chính phủ có thể sử dụng tự nguyện và tài liệu không thuộc bản quyền tại Hoa Kỳ; manifest ghi thông tin trích dẫn và ngày truy cập. Script trích xuất PDF, chỉ tính trang có ít nhất 1.500 ký tự, bỏ bìa/front matter, trang tài liệu tham khảo và trang quá ngắn; đồng thời gắn metadata section/revision. Script tạo `data/manifest.json` và `data/pages.jsonl`. Chạy lại script để tái tạo dữ liệu. Hình ảnh bị lược bỏ; bố cục bảng có thể không được giữ nguyên khi dùng pypdf.

Nếu Python không tải được PDF do lỗi chứng chỉ/mạng, tải PDF từ trang NIST chính thức vào `data/NIST.SP.800-61r3.pdf`, rồi chạy lại script để trích xuất.

`benchmark/questions.jsonl` có 20 câu tiếng Việt cùng đáp án, chia 15 dev/5 test; 6 câu nêu filter chapter, gồm 2 câu test. Khi truy xuất, runner dùng bản dịch câu hỏi tiếng Anh tương ứng vì corpus và model embedding là tiếng Anh; nội dung benchmark và báo cáo vẫn bằng tiếng Việt. Trích dẫn evidence giữ nguyên tiếng Anh để đối chiếu chính xác với nguồn NIST. Script xác minh trích dẫn xuất hiện trong corpus và gán số trang PDF trước khi chạy. Không điều chỉnh cấu hình dựa trên test. Các câu không có filter sẽ chạy C mà không lọc.

## Chạy và đầu ra

```powershell
python -m src.run
```

Runner kiểm tra số lượng/field đầu vào, embedding các chunk, thay thế snapshot từng chiến lược trong vector store, truy xuất top-3 cho mỗi câu hỏi và tạo:

- `results/retrieval_traces.json`: câu hỏi, gold evidence, top-k chunk, text/metadata/score và cờ hit.
- `results/metrics.json`: Hit@1 và Evidence Hit@3 theo chiến lược và split, dạng số hit/tổng câu.
- `results/run_metadata.json`: model, số chiều, số chunk, thời gian, cấu hình và chi phí.
- `results/*_audit.csv`: đánh giá chunk coherence, metadata và grounding.

Hit tự động chỉ xác nhận evidence được trích dẫn có mặt trong chunk cùng trang gold; không thay thế đánh giá thủ công. Phần audit hiện có nhãn AI hỗ trợ, cần người học xem xét và tự giải thích. Chroma dùng chỉ mục HNSW lưu cục bộ; PostgreSQL xếp hạng cosine chính xác nếu không bật chỉ mục gần đúng.
