# DCA Grid: So sánh tài liệu mới nhất và script hiện tại

Ngày rà soát: `2026-05-14`

## Tài liệu đang mô tả gì

File [QuantDinger/strategy_DCA_Grid.md](/home/work/quant-dinger/QuantDinger/strategy_DCA_Grid.md) hiện không còn mô tả đầy đủ toàn bộ bot như các bản trước. Nội dung mới nhất tập trung vào 1 lõi toán học:

- Volume mỗi lệnh DCA tăng theo cấp số nhân: `Q_k = Q_0 * m^k` tại [strategy_DCA_Grid.md:134](/home/work/quant-dinger/QuantDinger/strategy_DCA_Grid.md:134)
- Giá mỗi lệnh DCA giảm theo cấp số nhân: `P_k = P_0 * (1 - d)^k` tại [strategy_DCA_Grid.md:139](/home/work/quant-dinger/QuantDinger/strategy_DCA_Grid.md:139)
- Giá entry trung bình sau `n` lần DCA là trung bình có trọng số theo amount:
  `P_bar_n = sum(Q_k * P_k) / sum(Q_k)` tại [strategy_DCA_Grid.md:144](/home/work/quant-dinger/QuantDinger/strategy_DCA_Grid.md:144)

Điểm quan trọng nhất: tài liệu đang định nghĩa “giá trung bình” theo giá trị vốn, không phải trung bình cộng đơn giản của các mức giá.

## Script hiện tại đang làm gì

File [QuantDinger/strategy_dca_grid_script.py](/home/work/quant-dinger/QuantDinger/strategy_dca_grid_script.py) là một bot hoàn chỉnh, gồm:

- Entry theo RSI / MA-RSI tại [strategy_dca_grid_script.py:42](/home/work/quant-dinger/QuantDinger/strategy_dca_grid_script.py:42) và [strategy_dca_grid_script.py:484](/home/work/quant-dinger/QuantDinger/strategy_dca_grid_script.py:484)
- DCA thêm khi giá chạm grid tại [strategy_dca_grid_script.py:296](/home/work/quant-dinger/QuantDinger/strategy_dca_grid_script.py:296) và [strategy_dca_grid_script.py:421](/home/work/quant-dinger/QuantDinger/strategy_dca_grid_script.py:421)
- Exit DCA từng phần theo layer cuối tại [strategy_dca_grid_script.py:266](/home/work/quant-dinger/QuantDinger/strategy_dca_grid_script.py:266) và [strategy_dca_grid_script.py:391](/home/work/quant-dinger/QuantDinger/strategy_dca_grid_script.py:391)
- Trailing stop và hard stop tại [strategy_dca_grid_script.py:247](/home/work/quant-dinger/QuantDinger/strategy_dca_grid_script.py:247), [strategy_dca_grid_script.py:257](/home/work/quant-dinger/QuantDinger/strategy_dca_grid_script.py:257), [strategy_dca_grid_script.py:372](/home/work/quant-dinger/QuantDinger/strategy_dca_grid_script.py:372), [strategy_dca_grid_script.py:382](/home/work/quant-dinger/QuantDinger/strategy_dca_grid_script.py:382)

## Các điểm khớp

1. Script có tracking `layers`, `amount`, `price`, `total_entry_value`, nên có đủ dữ liệu để tính giá entry trung bình có trọng số.

2. Script đã dùng amount tăng dần theo công thức lũy tiến ở `_next_dca_amount(...)` tại [strategy_dca_grid_script.py:603](/home/work/quant-dinger/QuantDinger/strategy_dca_grid_script.py:603).

3. Script tính ROI tổng hợp theo tổng giá trị vào và phần đã thoát tại [strategy_dca_grid_script.py:207](/home/work/quant-dinger/QuantDinger/strategy_dca_grid_script.py:207) và [strategy_dca_grid_script.py:326](/home/work/quant-dinger/QuantDinger/strategy_dca_grid_script.py:326), nên về nền tảng dữ liệu là khá tốt.

## Các điểm lệch chính

### 1. Sai khác lớn nhất: `exit_price` đang dùng trung bình cộng giá, không dùng trung bình có trọng số

Script hiện tại:

- tạo DCA mới rồi gọi `_stack_average_price(new_stack)` tại [strategy_dca_grid_script.py:301](/home/work/quant-dinger/QuantDinger/strategy_dca_grid_script.py:301) và [strategy_dca_grid_script.py:426](/home/work/quant-dinger/QuantDinger/strategy_dca_grid_script.py:426)
- `_stack_average_price(...)` chỉ tính `sum(price) / len(price)` tại [strategy_dca_grid_script.py:642](/home/work/quant-dinger/QuantDinger/strategy_dca_grid_script.py:642)

Trong khi tài liệu mới nhất yêu cầu logic trung bình phải là:

- `sum(amount * price) / sum(amount)` tại [strategy_DCA_Grid.md:144](/home/work/quant-dinger/QuantDinger/strategy_DCA_Grid.md:144)

Hệ quả:

- Nếu các amount DCA tăng dần, script hiện tại đánh giá `exit_price` thấp hơn hoặc cao hơn thực tế tùy cấu trúc stack, nhưng chắc chắn không còn là “average entry” đúng nghĩa trong tài liệu.
- Backtest sẽ cho tín hiệu `Exit DCA` khác với kỳ vọng theo tài liệu.

### 2. Công thức tăng volume trong script không mặc định khớp ví dụ tài liệu

Tài liệu ví dụ:

- `Q1 = Q0 * 1.1`
- `Q2 = Q0 * 1.1^2`
  tại [strategy_DCA_Grid.md:17](/home/work/quant-dinger/QuantDinger/strategy_DCA_Grid.md:17) và [strategy_DCA_Grid.md:84](/home/work/quant-dinger/QuantDinger/strategy_DCA_Grid.md:84)

Script mặc định:

- `dca_amount = 100.0`
- `dca_amount_multiplier = 1.05`
  tại [strategy_dca_grid_script.py:28](/home/work/quant-dinger/QuantDinger/strategy_dca_grid_script.py:28)

Điều này cho ra chuỗi mặc định:

- DCA1 = `Q0 * 1.0`
- DCA2 = `Q1 * 1.05`
- DCA3 = `Q2 * 1.05`

Muốn khớp ví dụ tài liệu `Q_k = Q0 * 1.1^k`, script phải dùng param khác, ví dụ:

- `dca_amount = 110`
- `dca_amount_multiplier = 1.0`

Nghĩa là: code có thể biểu diễn được mô hình tài liệu, nhưng default hiện tại không khớp tài liệu.

### 3. Công thức bước giá DCA trong script không giống mô hình tài liệu

Tài liệu mô tả:

- `P_k = P_0 * (1 - d)^k` tại [strategy_DCA_Grid.md:139](/home/work/quant-dinger/QuantDinger/strategy_DCA_Grid.md:139)

Script hiện tại:

- lần đầu dùng `anchor_price * (1 - base_step)` tại [strategy_dca_grid_script.py:514](/home/work/quant-dinger/QuantDinger/strategy_dca_grid_script.py:514)
- các lần sau dùng `last_price * (1 - base_step * dca_multiplier)` tại [strategy_dca_grid_script.py:518](/home/work/quant-dinger/QuantDinger/strategy_dca_grid_script.py:518)

Nghĩa là script đang dùng:

- khoảng DCA đầu là `d`
- các khoảng sau là `d * dca_multiplier`

chứ không phải chuỗi hình học đúng kiểu `P0 * (1-d)^k` như tài liệu.

### 4. Tài liệu mới không nói gì về RSI entry, trailing, hard stop, short

Script vẫn có thêm:

- điều kiện vào lệnh RSI / MA-RSI
- trailing stop
- hard stop-loss
- nhánh short

Các phần này không sai theo nghĩa “bot”, nhưng không thể xem là đã được tài liệu mới xác nhận. Hiện tại chúng là logic bổ sung ngoài tài liệu.

## Kết luận

Nếu lấy [strategy_DCA_Grid.md](/home/work/quant-dinger/QuantDinger/strategy_DCA_Grid.md) làm chuẩn mới nhất, thì script hiện tại chưa khớp ở 3 điểm cốt lõi:

1. `exit_price` phải là trung bình có trọng số theo amount, nhưng script đang dùng trung bình cộng giá.
2. Chuỗi amount mặc định chưa khớp ví dụ `Q_k = Q_0 * m^k`.
3. Chuỗi giá DCA trong script chưa khớp công thức `P_k = P_0 * (1 - d)^k`.

Điểm lệch nghiêm trọng nhất là mục `1`, vì nó làm thay đổi trực tiếp mức giá hồi để bot thoát DCA.

## Phương án xử lý đề xuất

### Phương án A: Bám tài liệu mới nhất làm chuẩn

Nên làm nếu bạn xác nhận file `strategy_DCA_Grid.md` là nguồn chân lý mới.

Các việc cần sửa:

1. Đổi `_stack_average_price(...)` thành hàm tính average entry có trọng số:
   - `sum(layer.amount * layer.price) / sum(layer.amount)`
2. Khi add DCA mới, set `exit_price` của layer mới bằng weighted average của cả stack.
3. Sửa `_next_long_dca_price` và `_next_short_dca_price` để bám đúng chuỗi:
   - `P_k = P_0 * (1 - d)^k`
   - `P_k = P_0 * (1 + d)^k` cho short
4. Chốt lại mapping tham số volume để khớp tài liệu:
   - hoặc giữ `dca_amount` / `dca_amount_multiplier` nhưng đổi default
   - hoặc đổi sang một param rõ nghĩa hơn như `volume_multiplier`

Ưu điểm:

- Khớp tài liệu.
- Dễ audit backtest hơn.

Nhược điểm:

- Hành vi backtest sẽ thay đổi rõ, đặc biệt ở `Exit DCA`.

### Phương án B: Giữ bot hiện tại, sửa lại tài liệu cho khớp code

Nên làm nếu bạn xác nhận script hiện hành mới là thứ muốn giữ.

Các việc cần làm:

1. Viết lại tài liệu để mô tả rõ:
   - average exit đang là trung bình cộng giá
   - bước DCA dùng `dca_multiplier`
   - volume DCA dùng `dca_amount` + `dca_amount_multiplier`
2. Ghi rõ rằng đây là tài liệu của bot hoàn chỉnh, không chỉ là công thức trung bình giá.

Ưu điểm:

- Ít rủi ro làm thay đổi kết quả backtest hiện tại.

Nhược điểm:

- Tài liệu sẽ khác bản mô hình toán mà bạn vừa xác nhận là “logic mới nhất”.

## Khuyến nghị

Khuyến nghị chọn **Phương án A**.

Lý do:

- Người dùng đã xác nhận `strategy_DCA_Grid.md` là logic mới nhất.
- Tài liệu mới cho thấy trọng tâm là “giá trung bình có trọng số”, nên script hiện tại đang lệch ngay chỗ quan trọng nhất.
- Nếu không sửa theo tài liệu, các lần phân tích log/backtest tiếp theo sẽ tiếp tục bị lệch kỳ vọng.
