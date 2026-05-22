---
inclusion: auto
---

# Quy tắc theo dõi tiến độ — Fincept API Project

Mỗi khi bạn hoàn thành một nhiệm vụ trong dự án này, bạn **BẮT BUỘC** phải thực hiện hai hành động sau trước khi kết thúc phiên làm việc:

## 1. Cập nhật WORKLOGS.md

File: `g:\Code\AI-APP\FinceptTerminal\WORKLOGS.md`

Thêm một entry mới theo đúng format sau vào **đầu** phần "## Nhật ký công việc" (mới nhất lên trên):

```
### [YYYY-MM-DD HH:MM] — <Tên task ngắn gọn>

**Task ID:** <Phase>-<Task> (ví dụ: P0-T1, P1-T3)
**Phase:** Phase <N> — <Tên Phase>
**Trạng thái:** ✅ Hoàn thành | 🔄 Đang làm | ❌ Blocked
**Thời gian thực hiện:** <X phút/giờ>

**Đã làm:**
- <Mô tả cụ thể việc đã làm, file đã tạo/sửa>
- <...>

**Kết quả:**
- <Output, file được tạo, endpoint hoạt động, test pass...>

**Ghi chú / Vấn đề gặp phải:**
- <Nếu có vấn đề, blocked, hoặc quyết định kỹ thuật quan trọng>

---
```

## 2. Đánh checkbox trong PLAN.md

File: `g:\Code\AI-APP\FinceptTerminal\PLAN.md`

### Quy tắc đánh checkbox

Khi một task **hoàn thành hoàn toàn**:
- Đổi `- [ ]` → `- [x]` cho task đó trong PLAN.md

Khi một task **đang thực hiện** (chưa xong):
- Giữ nguyên `- [ ]`, KHÔNG đánh checkbox

### Quy tắc cập nhật trạng thái Phase

Khi **tất cả tasks trong một Phase** đã được đánh `[x]`:
- Cập nhật bảng tổng quan ở đầu file:
  - `⬜ Chưa bắt đầu` → `🔄 Đang làm` (khi bắt đầu task đầu tiên)
  - `🔄 Đang làm` → `✅ Hoàn thành` (khi tất cả tasks xong)
- Cập nhật dòng `> **Trạng thái:**` trong header của Phase đó

### Quy tắc cập nhật Deliverables

Khi một Deliverable đã đạt được:
- Đổi `- [ ]` → `- [x]` trong phần "### Deliverables Phase N"

## 3. Ví dụ thực tế

Sau khi hoàn thành task P0-T1 (Khởi tạo FastAPI project skeleton):

**Trong WORKLOGS.md, thêm:**
```
### [2026-05-19 10:30] — Khởi tạo FastAPI project skeleton

**Task ID:** P0-T1
**Phase:** Phase 0 — Foundation & Setup
**Trạng thái:** ✅ Hoàn thành
**Thời gian thực hiện:** 45 phút

**Đã làm:**
- Tạo `fincept-api/app/main.py` với FastAPI app và health check endpoint
- Tạo `fincept-api/app/config.py` với Pydantic Settings
- Cấu hình CORS middleware cho localhost:3000 và *
- Thêm structured logging với uvicorn

**Kết quả:**
- `GET /health` trả `{"status": "ok", "version": "1.0.0"}`
- Server khởi động thành công với `uvicorn app.main:app --reload`

**Ghi chú:**
- Dùng Pydantic v2 Settings thay v1 vì project yêu cầu Python 3.11+

---
```

**Trong PLAN.md, đổi:**
```
- [x] **P0-T1** Khởi tạo FastAPI project skeleton
```

## 4. Lưu ý quan trọng

- **KHÔNG** bỏ qua bước cập nhật WORKLOGS.md và PLAN.md dù task nhỏ đến đâu
- **KHÔNG** đánh `[x]` cho task chưa hoàn thành hoàn toàn
- Nếu task bị **blocked**, ghi rõ lý do trong WORKLOGS.md và thêm note vào PLAN.md
- Nếu phát hiện task cần **chia nhỏ hơn**, ghi vào WORKLOGS.md và đề xuất cập nhật PLAN.md
- Timestamp dùng **múi giờ local** của máy (không cần UTC)
