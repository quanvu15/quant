Đã rõ — tôi cập nhật lại hiểu đúng như sau:

## Chốt lại yêu cầu TP
**Take Profit phải luôn được kiểm tra theo `InitRoi` ở mọi thời điểm**, kể cả khi:
- đang có nhiều layer DCA,
- vừa exit DCA xong,
- rồi lại DCA tiếp,
- rồi lại exit tiếp.

Tức là **không chờ đến khi chỉ còn entry layer** mới xét TP.

Nói cách khác:

### TP global luôn-on
Với LONG:
\[
ROI = \frac{price * remaining + total\_exit\_value - total\_entry\_value}{total\_entry\_value} * 100
\]

Nếu:
\[
ROI \ge InitRoi
\]
thì chiến lược có thể:
- kích hoạt trailing nếu `use_trailing=true`
- hoặc đóng toàn bộ vị thế nếu không dùng trailing

Điều này áp dụng **ở mọi trạng thái stack**.

---

# SPEC CHI TIẾT: DCA / EXIT DCA / TP

Dưới đây là bản spec rõ ràng để chốt logic trước khi sửa code.

---

## 1. Mục tiêu chiến lược

Chiến lược LONG DCA Grid hoạt động theo thứ tự ưu tiên:

1. **Mở lệnh entry** khi có tín hiệu vào lệnh.
2. **Luôn kiểm tra TP theo `InitRoi` trên toàn bộ vị thế hiện tại**.
3. Nếu chưa TP:
   - kiểm tra trailing stop / hard stop
   - kiểm tra exit DCA của layer mới nhất
   - kiểm tra add DCA mới
4. Quản lý stack theo kiểu **LIFO**:
   - DCA mới nhất được thoát trước.

---

## 2. Dữ liệu trạng thái cần có

### Input runtime / state
- `layers`: danh sách layer đang active
- `total_entry_value`: tổng giá trị đã vào
- `total_exit_value`: tổng giá trị đã thoát từng phần
- `entry_price`: giá entry ban đầu
- `position.side`
- `position.size`

### Mỗi layer gồm:
- `kind`: `entry` hoặc `dca`
- `price`: giá khớp của layer
- `amount`: amount của layer
- `exit_price`: giá target để exit layer này

---

## 3. Quy tắc Entry

### Điều kiện vào LONG
Theo RSI / MA-RSI như hiện tại.

### Khi entry:
Tạo layer đầu tiên:

| field | value |
|---|---|
| kind | `entry` |
| price | giá entry |
| amount | entry amount |
| exit_price | chính giá entry hoặc 0, không quan trọng cho exit DCA |

Đồng thời:
- `total_entry_value += entry_price * entry_amount`
- `total_exit_value = 0`

---

## 4. Quy tắc Add DCA

### Điều kiện add LONG
Nếu:
\[
current\_price \le next\_dca\_price
\]

Trong đó:

- Nếu chưa có DCA nào:
\[
next\_dca\_price = entry\_price * (1 - dca\_grid\_pct/100)
\]

- Nếu đã có DCA:
\[
next\_dca\_price = last\_layer.price * (1 - dca\_grid\_pct/100 * dca\_multiplier)
\]

### Amount DCA
- DCA1:
\[
dca\_amount_1 = entry\_amount * dca\_amount / 100
\]

- DCA kế tiếp:
\[
dca\_amount_n = last\_dca\_amount * dca\_amount / 100 * dca\_amount\_multiplier
\]

---

## 5. Quy tắc Exit DCA mới

### Rule chính
Khi thêm một DCA layer mới, `exit_price` của layer đó sẽ là:

\[
exit\_price = average(price của tất cả active layers sau khi đã add layer mới)
\]

### Công thức
Nếu stack hiện tại có các giá:
\[
p_1, p_2, ..., p_n
\]

thì:
\[
exit\_price = \frac{p_1 + p_2 + ... + p_n}{n}
\]

### Lưu ý
- Đây là **trung bình cộng đơn giản theo giá**
- **không weighted theo amount**
- chỉ layer **mới nhất** được kiểm tra exit trước
- exit theo **LIFO**

---

## 6. Điều kiện Exit DCA

Với LONG:

- lấy `last_layer = layers[-1]`
- nếu `last_layer.kind == 'dca'`
- và:
\[
current\_price \ge last\_layer.exit\_price
\]

thì:
- thoát đúng `amount` của layer đó
- cộng vào:
\[
total\_exit\_value += current\_price * last\_layer.amount
\]
- remove layer đó khỏi stack

### Amount thoát
Thoát đúng amount của chính layer DCA mới nhất:
\[
reduce\_amount = last\_layer.amount
\]

Nếu engine cần ratio:
\[
reduce\_ratio = \frac{last\_layer.amount}{\sum active\_layer.amount}
\]

---

## 7. Quy tắc Take Profit — luôn kiểm tra

### ROI tổng hợp cho LONG
Ở mọi thời điểm:

\[
remaining = \sum layer.amount
\]

\[
ROI = \frac{current\_price * remaining + total\_exit\_value - total\_entry\_value}{total\_entry\_value} * 100
\]

### Rule TP
Nếu:
\[
ROI \ge InitRoi
\]

thì:
- nếu `use_trailing = false` → **đóng toàn bộ vị thế**
- nếu `use_trailing = true` → **kích hoạt / duy trì trailing**

### Ý nghĩa rất quan trọng
Điều này có nghĩa:
- có thể **chưa cần exit DCA** mà đã TP toàn bộ nếu ROI đủ
- hoặc đã exit vài DCA, sau đó ROI đủ thì vẫn TP toàn bộ phần còn lại
- TP là điều kiện **toàn cục**, không phụ thuộc số layer còn lại

---

## 8. Thứ tự kiểm tra trong mỗi bar/tick

Đây là thứ tự tôi đề xuất để đúng logic và tránh xung đột:

### Với LONG đang mở vị thế:

#### Bước 1 — Tính ROI tổng hợp
- từ `remaining`, `total_entry_value`, `total_exit_value`

#### Bước 2 — Kiểm tra TP global
- nếu `ROI >= InitRoi`
  - dùng trailing hoặc close toàn bộ
  - **ưu tiên cao hơn exit DCA**

#### Bước 3 — Kiểm tra hard stop / trailing stop
- nếu hit → close toàn bộ

#### Bước 4 — Kiểm tra Exit DCA
- chỉ check `layers[-1]`
- nếu là layer `dca` và `price >= exit_price` → reduce layer đó

#### Bước 5 — Kiểm tra Add DCA mới
- nếu chưa vượt `dca_max_count`
- nếu `price <= next_dca_price` → add layer mới

---

## 9. Input / Output spec

## Input
- `entry_price`
- `entry_amount`
- `dca_grid_pct`
- `dca_multiplier`
- `dca_amount`
- `dca_amount_multiplier`
- `init_roi_pct`
- `use_trailing`
- `trailing_pct`
- `stop_loss_pct`
- `dca_max_count`
- `current_price`
- `layers`
- `total_entry_value`
- `total_exit_value`

## Output có thể là 1 trong các action
- `open_long(amount, price)`
- `add_long(amount, price, exit_price)`
- `reduce_long(amount or ratio, price, target_layer)`
- `close_long(price, reason)`
- `hold`

---

# 10. Ví dụ step-by-step

---

## Ví dụ A — 2 layer
### Input
- Entry: `1000`, amount `100`
- DCA1: `990`, amount `100`

### Step 1
Stack:
- Entry(1000, 100)

### Step 2 — Add DCA1
Stack sau add:
- Entry(1000, 100)
- DCA1(990, 100)

Exit target của DCA1:
\[
(1000 + 990)/2 = 995
\]

### Step 3 — Exit DCA1
Nếu giá lên `995` hoặc hơn:
- thoát `100` của DCA1
- stack còn:
  - Entry(1000, 100)

### Step 4 — TP global
Luôn tính ROI tổng hợp.
Sau khi chỉ còn entry:
- nếu giá đạt mức làm ROI tổng >= `InitRoi` → TP toàn bộ.

---

## Ví dụ B — 3 layer
### Input
- Entry: `1000`, amount `100`
- DCA1: `990`, amount `101`
- DCA2: `980`, amount `102`

### Step 1
Stack:
- Entry(1000,100)

### Step 2 — Add DCA1
Stack:
- Entry(1000,100)
- DCA1(990,101)

Exit DCA1:
\[
(1000 + 990)/2 = 995
\]

### Step 3 — Add DCA2
Stack:
- Entry(1000,100)
- DCA1(990,101)
- DCA2(980,102)

Exit DCA2:
\[
(1000 + 990 + 980)/3 = 990
\]

### Step 4 — Giá hồi lên 990
- thoát DCA2 amount `102`
- stack còn:
  - Entry(1000,100)
  - DCA1(990,101)

### Step 5 — Giá hồi lên 995
- thoát DCA1 amount `101`
- stack còn:
  - Entry(1000,100)

### Step 6 — TP global
Bất kỳ lúc nào trong các bước trên, nếu ROI tổng hợp đạt `InitRoi`, thì TP/trailing có thể kích hoạt trước.

---

## Ví dụ C — 4 layer
### Input
- Entry: `1000`, amount `100`
- DCA1: `990`, amount `101`
- DCA2: `980`, amount `102`
- DCA3: `970`, amount `103`

### Step 1 — Stack đầy đủ
- Entry(1000,100)
- DCA1(990,101)
- DCA2(980,102)
- DCA3(970,103)

Exit DCA3:
\[
(1000 + 990 + 980 + 970)/4 = 985
\]

### Step 2 — Giá hồi lên 985
- thoát DCA3 amount `103`

Stack còn:
- Entry(1000,100)
- DCA1(990,101)
- DCA2(980,102)

Exit DCA2:
\[
(1000 + 990 + 980)/3 = 990
\]

### Step 3 — Giá hồi lên 990
- thoát DCA2 amount `102`

Stack còn:
- Entry(1000,100)
- DCA1(990,101)

Exit DCA1:
\[
(1000 + 990)/2 = 995
\]

### Step 4 — Giá hồi lên 995
- thoát DCA1 amount `101`

Stack còn:
- Entry(1000,100)

### Step 5 — TP global
Ở bất cứ lúc nào nếu:
\[
ROI \ge InitRoi
\]
thì đóng toàn bộ vị thế hoặc kích hoạt trailing.

---

## Ví dụ D — 4 layer nhưng TP xảy ra trước Exit DCA
### Input
- Entry 1000
- DCA1 990
- DCA2 980
- DCA3 970

Giả sử sau khi DCA3, giá bật mạnh lên 1002.

Lúc này:
- DCA3 có exit target = 985
- nhưng ROI tổng hợp có thể đã vượt `InitRoi`

### Rule đúng
- **TP global được ưu tiên**
- nếu đã đạt `InitRoi`:
  - close toàn bộ / trailing
  - **không cần phải exit DCA từng lớp nữa**

Đây là điểm quan trọng để tránh “thoát lắt nhắt” khi toàn vị thế đã đủ lợi nhuận.

---

# 11. Pseudo-code chuẩn hóa

```text
if no position:
    if entry signal:
        open entry layer
    return

sync state
compute remaining
compute total ROI

# 1. TP global luôn check trước
if ROI >= InitRoi:
    if use_trailing:
        activate/update trailing
        if trailing hit:
            close all
            reset
            return
    else:
        close all
        reset
        return

# 2. hard stop
if hard stop hit:
    close all
    reset
    return

# 3. exit DCA top layer
if use_exit_dca and len(layers) > 1:
    top = layers[-1]
    if top.kind == 'dca' and current_price >= top.exit_price:
        reduce top.amount
        total_exit_value += current_price * top.amount
        pop top
        return

# 4. add next DCA
if dca_count < dca_max_count and current_price <= next_dca_price:
    amount = next_dca_amount()
    push new dca layer
    new_layer.exit_price = average(all active layer prices)
    total_entry_value += current_price * amount
    return
```

---

# 12. Những điểm cần bạn xác nhận trước khi sửa code

Tôi cần bạn chốt 3 điểm nhỏ này:

### Câu hỏi 1
**Exit DCA average** dùng:
- **A. trung bình giá đơn giản** `(p1+p2+...+pn)/n`
- hay
- **B. trung bình giá theo amount** `Σ(price*amount)/Σ(amount)`

Hiện tôi đang hiểu là **A**.

### Câu hỏi 2
Khi **ROI đã đạt InitRoi**, có đúng là:
- **ưu tiên close/trailing toàn bộ**
- không cần exit DCA từng lớp nữa

Hiện tôi đang hiểu là **đúng**.

### Câu hỏi 3
Sau khi exit một DCA layer, nếu giá lại giảm tiếp thì có được:
- add DCA lại bình thường theo stack mới không?

Hiện tôi đang hiểu là **có**.

