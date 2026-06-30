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
            [InlineKeyboardButton(text="➕ Thêm kênh gate", callback_data="cfg_gate")],
            [InlineKeyboardButton(text="➕ Thêm kênh đích", callback_data="cfg_target_add")],
            [InlineKeyboardButton(text="🔗 Gán gate cho kênh đích", callback_data="cfg_link_gate")],
            [InlineKeyboardButton(text="📋 Xem tất cả kênh", callback_data="cfg_list")],
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
