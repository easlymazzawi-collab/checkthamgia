# checkthamgia

Tool kiểm tra & tự duyệt tham gia kênh Telegram — Bot + Userbot + kho dữ liệu **clender**.

## Tính năng

| Tính năng | Mô tả |
|-----------|--------|
| **Folder → Gate** | Mỗi folder Telegram có **1 kênh gate riêng** — member phải vào gate đó |
| **Đa folder** | Folder A → gate A, Folder B → gate B; kênh trong folder tự gắn gate |
| **Tự duyệt (Bot)** | Bot duyệt join request khi member vào **đúng gate** của kênh đích |
| **Userbot** | Chỉ dùng mời bot vào kênh qua folder Telegram, không duyệt |
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
2. **Cấu hình** → thêm nhiều gate + kênh đích, gán gate cho từng kênh (bật join request)
3. **Mời bot (folder)** → userbot add bot vào kênh (bot cần quyền admin sau đó)
4. **Bot** phải là admin kênh gate & đích, có quyền **Invite users via link** / duyệt join request
5. Userbot account chỉ cần quyền add member vào kênh (để mời bot)

## Luồng tự duyệt

```
Member gửi join request kênh đích
        ↓
Member vào kênh gate (chỉ định)
        ↓
Bot phát hiện (chat_member) → approve_chat_join_request
        ↓
Cập nhật clender DB + thông báo admin
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
├── bot/
│   ├── handlers.py      # UI admin, broadcast, stats
│   ├── approval.py      # Bot tự duyệt join request
│   ├── keyboards.py
│   └── broadcast_state.py
└── userbot/
    └── service.py       # Chỉ mời bot qua folder
└── services/
    └── backup.py
```

## Yêu cầu quyền

- **Bot**: admin kênh gate & đích, quyền duyệt join request + nhận `chat_join_request` / `chat_member`
- **Userbot**: chỉ add bot vào kênh qua folder (quyền invite/add member)

## Biến môi trường

| Biến | Mô tả |
|------|--------|
| `BOT_TOKEN` | Token BotFather |
| `API_ID`, `API_HASH` | my.telegram.org (userbot) |
| `ADMIN_IDS` | ID admin, phân cách bằng dấu phẩy |
| `BACKUP_INTERVAL_HOURS` | Chu kỳ backup (mặc định 6) |
| `BROADCAST_IDLE_SECONDS` | Giây chờ trước hỏi xác nhận broadcast (mặc định 1) |
