# Patch UpBain v26 — fix TypeError `get_pinned_message_id`

Lỗi khi **Chạy full (topic + /all)**:

```
❌ Lỗi Chạy full (topic + /all): TypeError
SearchMessages.search_messages() got an unexpected keyword argument 'reply_to_message_id'
```

## Cách sửa nhanh (Windows)

1. Mở CMD **trong thư mục UpBain** (cùng cấp `tool__tauto_nostage.py`)
2. Copy thư mục `upbain-patch` vào đó (từ repo checkthamgia)
3. Chạy:

```cmd
upbain-patch\apply-fix.bat
```

4. Tắt tool → chạy lại

## Hoặc pull branch UpBain

```cmd
git pull origin cursor/fix-pinned-typeerror-9fbc
```

## Sửa tay

Copy 3 file trong `core/` vào thư mục `core\` của UpBain:

```
core/forum_api.py          ← file MỚI
core/pin_manager.py        ← thay file cũ
core/source_collector.py   ← thay file cũ
```

## Nguyên nhân

Code cũ gọi `search_messages(..., reply_to_message_id=topic_id)` — Pyrogram **không có** tham số này. Cả fallback trong `except TypeError` cũng dùng lại `reply_to_message_id` nên **vẫn lỗi**.

Patch dùng raw API `messages.Search` với `top_msg_id` cho forum topic.
