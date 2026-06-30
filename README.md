# checkthamgia

Tool kiểm tra & tự duyệt tham gia kênh Telegram — Bot + Userbot + kho dữ liệu **clender**.

## Tính năng

| Tính năng | Mô tả |
|-----------|--------|
| **Kênh chỉ định (gate)** | Member muốn vào kênh đích phải vào kênh gate trước |
| **Tự duyệt** | Userbot phát hiện member vào gate → tự approve join request, không cần bấm nút |
| **Mời bot qua folder** | Userbot quét folder Telegram, mời bot vào các kênh |
| **Cập nhật dữ liệu** | Lưu user/events vào SQLite (`clender.db`), thông báo admin qua bot |
| **Broadcast** | Copy message, gửi nhiều bài, bấm Done → chờ 1s → xác nhận → gửi |
| **Thống kê** | Số người vào gate, đã duyệt, log ai vào khi nào |
| **Backup** | Tự động theo giờ (cấu hình được), gửi file JSON + DB cho admin |

## Cài đặt

```bash
pip install -r requirements.txt
cp .env.example .env
# Sửa .env: BOT_TOKEN, API_ID, API_HASH, ADMIN_IDS
```

### Lần đầu chạy userbot

Userbot cần đăng nhập Telegram (my.telegram.org):

```bash
python main.py
```

Nhập số điện thoại và mã OTP khi được hỏi. Session lưu tại `data/checkthamgia.session`.

## Cấu hình bot

1. `/start` — menu admin
2. **Cấu hình** → Set kênh chỉ định (gate) và kênh đích (bật join request)
3. **Mời bot (folder)** → nhập tên folder Telegram để userbot mời bot vào kênh
4. Userbot account phải là admin kênh đích (quyền duyệt thành viên)

## Luồng tự duyệt

```
Member gửi join request kênh đích
        ↓
Member vào kênh gate (chỉ định)
        ↓
Userbot phát hiện → HideChatJoinRequest (approve)
        ↓
Cập nhật clender DB + thông báo admin bot
```

## Broadcast

1. Bấm **📢 Broadcast**
2. Gửi/chuyển tiếp các bài (bao nhiêu cũng được)
3. Bấm **Done** — bot chờ 1 giây không có tin mới
4. Xác nhận → gửi `copy_message` tới toàn bộ user trong DB

## Backup

- Mặc định mỗi 6 giờ (`.env`: `BACKUP_INTERVAL_HOURS`)
- Đổi trong bot: **Cấu hình** → Set giờ backup
- **Backup ngay** — gửi ngay cho admin

## Cấu trúc

```
checkthamgia/
├── main.py              # Entry: bot + userbot + scheduler
├── config.py
├── clender/
│   └── database.py      # Kho dữ liệu SQLite
├── userbot/
│   └── service.py       # Folder invite, auto-approve
├── bot/
│   ├── handlers.py      # UI admin, broadcast, stats
│   ├── keyboards.py
│   └── broadcast_state.py
└── services/
    └── backup.py
```

## Yêu cầu quyền

- **Userbot**: admin kênh gate & đích, quyền `invite_users` + duyệt join request
- **Bot**: admin kênh (nếu cần), dùng cho UI và broadcast PM

## Biến môi trường

| Biến | Mô tả |
|------|--------|
| `BOT_TOKEN` | Token BotFather |
| `API_ID`, `API_HASH` | my.telegram.org (userbot) |
| `ADMIN_IDS` | ID admin, phân cách bằng dấu phẩy |
| `BACKUP_INTERVAL_HOURS` | Chu kỳ backup (mặc định 6) |
| `BROADCAST_IDLE_SECONDS` | Giây chờ trước hỏi xác nhận broadcast (mặc định 1) |
