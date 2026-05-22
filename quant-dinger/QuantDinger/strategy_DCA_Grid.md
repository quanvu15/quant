Giả sử:

- **Vị thế ban đầu**: `Q0 = 0.1 BTC`
- **Đòn bẩy**: `L = 10x`
- **Giá vào lệnh ban đầu**: `P0 = 80,000 USDT`
- **Multiplier volume mỗi lần DCA**: `m = 1.1`  (tăng 10%)
- **Khoảng cách DCA mỗi lần**: giảm `d = 2% = 0.02`

Ta cần tính **giá entry trung bình sau mỗi lần DCA**.

## 1) Công thức tổng quát

Sau `n` lần DCA:

- Khối lượng mỗi lệnh:
  - Lệnh 0: `Q0`
  - Lệnh 1: `Q1 = Q0 * m`
  - Lệnh 2: `Q2 = Q0 * m^2`
  - ...
  - Lệnh `n`: `Qn = Q0 * m^n`

- Giá mỗi lệnh:
  - `P0`
  - `P1 = P0 * (1 - d)`
  - `P2 = P0 * (1 - d)^2`
  - ...
  - `Pn = P0 * (1 - d)^n`

- **Giá entry trung bình sau n lần DCA**:

\[
\bar P_n = \frac{\sum_{k=0}^{n} Q_0 m^k \cdot P_0(1-d)^k}{\sum_{k=0}^{n} Q_0 m^k}
\]

Rút gọn:

\[
\bar P_n = P_0 \cdot \frac{\sum_{k=0}^{n} [m(1-d)]^k}{\sum_{k=0}^{n} m^k}
\]

---

## 2) Tính từng lần với dữ liệu của bạn

### Ban đầu
- Entry trung bình ban đầu:  
\[
\bar P_0 = 80,000
\]

---

### DCA lần 1
- Volume: `Q1 = 0.1 * 1.1 = 0.11 BTC`
- Giá DCA 1:
\[
P_1 = 80,000 \times 0.98 = 78,400
\]

Entry trung bình mới:

\[
\bar P_1 = \frac{0.1 \cdot 80,000 + 0.11 \cdot 78,400}{0.1 + 0.11}
\]

Tính ra:

- `0.1 * 80,000 = 8,000`
- `0.11 * 78,400 = 8,624`
- Tổng = `16,624`
- Tổng volume = `0.21`

\[
\bar P_1 = \frac{16,624}{0.21} \approx 79,161.90
\]

**Entry sau DCA 1: ~ 79,161.90 USDT**

---

### DCA lần 2
- Volume:
\[
Q_2 = 0.11 \times 1.1 = 0.121 BTC
\]

- Giá DCA 2:
\[
P_2 = 78,400 \times 0.98 = 76,832
\]

Entry trung bình mới:

\[
\bar P_2 = \frac{0.1 \cdot 80,000 + 0.11 \cdot 78,400 + 0.121 \cdot 76,832}{0.1 + 0.11 + 0.121}
\]

Tính:

- `0.1 * 80,000 = 8,000`
- `0.11 * 78,400 = 8,624`
- `0.121 * 76,832 = 9,295.552`
- Tổng = `25,919.552`
- Tổng volume = `0.331`

\[
\bar P_2 = \frac{25,919.552}{0.331} \approx 78,312.01
\]

**Entry sau DCA 2: ~ 78,312.01 USDT**

---

## 3) Kết quả tóm tắt

- **Entry ban đầu**: `80,000`
- **Sau DCA 1**: `~79,161.90`
- **Sau DCA 2**: `~78,312.01`

---

## 4) Công thức tổng quát dễ dùng

Nếu:

- `P0` = giá entry ban đầu
- `Q0` = volume ban đầu
- `m` = hệ số tăng volume mỗi DCA
- `d` = mức giảm giá mỗi DCA
- `n` = số lần DCA

thì:

### Volume lệnh thứ k:
\[
Q_k = Q_0 m^k
\]

### Giá lệnh thứ k:
\[
P_k = P_0 (1-d)^k
\]

### Giá entry trung bình sau n lần:
\[
\bar P_n = \frac{\sum_{k=0}^{n} Q_0 m^k P_0(1-d)^k}{\sum_{k=0}^{n} Q_0 m^k}
\]

Rút gọn:
\[
\bar P_n = P_0 \cdot \frac{\sum_{k=0}^{n} [m(1-d)]^k}{\sum_{k=0}^{n} m^k}
\]

---
