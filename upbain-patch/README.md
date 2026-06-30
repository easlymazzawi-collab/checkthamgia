# Patch UpBain v26 — fix TypeError `get_pinned_message_id`

Lỗi khi **Chạy full (topic + /all)**:

```
SearchMessages.search_messages() got an unexpected keyword argument 'reply_to_message_id'
```

## Cách sửa

Copy 3 file trong `core/` vào thư mục tool UpBain (cùng cấp `tool__tauto_nostage.py`):

```
core/forum_api.py          ← file mới
core/pin_manager.py        ← thay file cũ
core/source_collector.py   ← thay file cũ
```

Rồi chạy lại tool.

## Nguyên nhân

Pyrogram `search_messages()` **không có** tham số `reply_to_message_id`.
Patch dùng raw API `messages.Search` với `top_msg_id` cho forum topic.
