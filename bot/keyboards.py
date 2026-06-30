from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton


def admin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Thống kê"), KeyboardButton(text="📢 Broadcast")],
            [KeyboardButton(text="⚙️ Cấu hình"), KeyboardButton(text="📁 Mời bot (folder)")],
            [KeyboardButton(text="🔍 Quét duyệt"), KeyboardButton(text="💾 Backup ngay")],
        ],
        resize_keyboard=True,
    )


def config_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📂 Set gate cho folder", callback_data="cfg_folder_gate")],
            [InlineKeyboardButton(text="➕ Thêm kênh đích (lẻ)", callback_data="cfg_target_add")],
            [InlineKeyboardButton(text="📋 Xem folder & kênh", callback_data="cfg_list")],
            [InlineKeyboardButton(text="✏️ Tin nhắn member", callback_data="cfg_member_msg")],
            [InlineKeyboardButton(text="Set giờ backup", callback_data="cfg_backup_hours")],
        ]
    )


def broadcast_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Done - Gửi broadcast", callback_data="bc_done")],
            [InlineKeyboardButton(text="❌ Hủy", callback_data="bc_cancel")],
        ]
    )


def confirm_broadcast(count: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=f"✅ Xác nhận gửi {count} bài", callback_data="bc_confirm"),
                InlineKeyboardButton(text="❌ Hủy", callback_data="bc_cancel"),
            ]
        ]
    )
