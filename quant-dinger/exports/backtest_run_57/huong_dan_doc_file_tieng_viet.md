# Huong dan doc file logic backtest #57

File chinh:
- run_57_logic_tieng_viet.csv

Cach doc nhanh:
- `Lenh goc`: lenh raw engine da luu, vi du `add_long`, `reduce_long`, `close_long`
- `Hanh dong theo logic chien luoc`: cach dien giai de nguoi doc hieu no dang lam gi
- `Layer dang tac dong`: layer DCA dang duoc them vao hoac thoat ra
- `Layer truoc no`: layer nam ngay duoi trong stack DCA
- `Gia trigger dung theo chien luoc`: neu dung logic DCA exit chuan thi gia phai hoi ve muc nay moi nen thoat
- `Gia trigger theo log cu`: gia ma run #57 thuc te dang co xu huong thoat theo
- `Khop voi mo hinh nao`: dong nay dang gan logic dung hay gan logic cu
- `Ghi chu de hieu`: ket luan ngan gon cho tung dong

Cach nhin ra loi nhanh:
- Neu `Khop voi mo hinh nao` = `Gan voi logic cu: thoat theo gia cua chinh layer vua add` thi dong do lech voi logic DCA exit chuan.
- Neu `Gia khop thuc te` van thap hon `Gia trigger dung theo chien luoc` ma van co dong `Thoat layer DCA moi nhat`, thi do la thoat som.
