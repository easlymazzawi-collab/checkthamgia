"""Bot chính: giao diện admin, broadcast, thống kê."""

from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message

import config
from bot.broadcast_state import clear_session, get_session
from bot.keyboards import admin_menu, broadcast_menu, config_menu, confirm_broadcast
from clender.database import ClenderDB
from services.backup import send_backup_to_admins

logger = logging.getLogger(__name__)

router = Router()


class ConfigStates(StatesGroup):
    waiting_gate = State()
    waiting_target = State()
    waiting_backup_hours = State()
    waiting_folder_name = State()


class BroadcastStates(StatesGroup):
    collecting = State()


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


def setup_handlers(dp: Dispatcher, db: ClenderDB, userbot_service=None) -> None:
    dp.include_router(router)

    @router.message(CommandStart())
    async def cmd_start(message: Message) -> None:
        if not is_admin(message.from_user.id):
            await message.answer("⛔ Bạn không có quyền truy cập.")
            return
        await message.answer(
            "👋 Check Tham Gia Bot\n\n"
            "• Member muốn vào kênh đích → phải vào kênh chỉ định trước\n"
            "• Userbot tự duyệt join request khi phát hiện vào kênh gate\n"
            "• Broadcast bằng copy message\n"
            "• Backup tự động theo giờ cấu hình",
            reply_markup=admin_menu(),
        )

    @router.message(F.text == "📊 Thống kê")
    async def stats(message: Message) -> None:
        if not is_admin(message.from_user.id):
            return
        s = await db.stats_summary()
        gate_id = await db.get_gate_channel_id()
        targets = await db.list_channels("target")
        recent = await db.recent_events(15)

        lines = [
            "📊 **Thống kê**",
            f"👥 Tổng user trong DB: {s['total_users']}",
            f"🚪 Vào kênh chỉ định: {s['gate_joined']} (events: {s['gate_events']})",
            f"✅ Đã duyệt: {s['approved']} (events: {s['approve_events']})",
            f"🎯 Kênh gate: `{gate_id or 'chưa set'}`",
            f"📢 Kênh đích: {len(targets)}",
            "",
            "**Gần đây:**",
        ]
        for ev in recent:
            lines.append(
                f"• [{ev['event_type']}] @{ev['username'] or ev['user_id']} "
                f"— {ev['created_at'][:19]}"
            )
        await message.answer("\n".join(lines), parse_mode="Markdown")

    @router.message(F.text == "⚙️ Cấu hình")
    async def config_cmd(message: Message) -> None:
        if not is_admin(message.from_user.id):
            return
        hours = await db.get_setting("backup_interval_hours", str(config.BACKUP_INTERVAL_HOURS))
        await message.answer(
            f"⚙️ Cấu hình\nBackup mỗi: **{hours}h**",
            reply_markup=config_menu(),
            parse_mode="Markdown",
        )

    @router.callback_query(F.data == "cfg_gate")
    async def cfg_gate(cb: CallbackQuery, state: FSMContext) -> None:
        await cb.answer()
        await state.set_state(ConfigStates.waiting_gate)
        await cb.message.answer(
            "Gửi ID hoặc @username kênh **chỉ định** (gate).\n"
            "Member phải vào kênh này trước khi được duyệt."
        )

    @router.message(ConfigStates.waiting_gate)
    async def set_gate(message: Message, state: FSMContext) -> None:
        text = message.text.strip()
        chat_id = None
        title = text
        if userbot_service and userbot_service.client:
            try:
                ent = await userbot_service.client.get_entity(text)
                chat_id = ent.id
                if hasattr(ent, "title"):
                    title = ent.title
                # normalize supergroup id
                from telethon.tl.types import Channel

                if isinstance(ent, Channel):
                    chat_id = int(f"-100{ent.id}")
            except Exception as e:
                await message.answer(f"❌ Không lấy được kênh: {e}")
                return
        else:
            try:
                chat_id = int(text)
            except ValueError:
                await message.answer("❌ Cần userbot online hoặc gửi numeric chat_id")
                return

        await db.set_gate_channel_id(chat_id)
        await db.add_channel(chat_id, title, "gate")
        await state.clear()
        await message.answer(f"✅ Kênh chỉ định: {title} (`{chat_id}`)", parse_mode="Markdown")

    @router.callback_query(F.data == "cfg_target_add")
    async def cfg_target(cb: CallbackQuery, state: FSMContext) -> None:
        await cb.answer()
        await state.set_state(ConfigStates.waiting_target)
        await cb.message.answer("Gửi ID hoặc @username **kênh đích** (có bật join request).")

    @router.message(ConfigStates.waiting_target)
    async def set_target(message: Message, state: FSMContext) -> None:
        text = message.text.strip()
        if userbot_service and userbot_service.client:
            try:
                ent = await userbot_service.client.get_entity(text)
                from telethon.tl.types import Channel

                chat_id = int(f"-100{ent.id}") if isinstance(ent, Channel) else ent.id
                title = getattr(ent, "title", text)
                await db.add_channel(chat_id, title, "target")
                await state.clear()
                await message.answer(f"✅ Thêm kênh đích: {title} (`{chat_id}`)", parse_mode="Markdown")
            except Exception as e:
                await message.answer(f"❌ {e}")
        else:
            try:
                chat_id = int(text)
                await db.add_channel(chat_id, text, "target")
                await state.clear()
                await message.answer(f"✅ Thêm kênh đích `{chat_id}`", parse_mode="Markdown")
            except ValueError:
                await message.answer("❌ Cần userbot hoặc numeric id")

    @router.callback_query(F.data == "cfg_list")
    async def cfg_list(cb: CallbackQuery) -> None:
        await cb.answer()
        channels = await db.list_channels()
        if not channels:
            await cb.message.answer("Chưa có kênh nào")
            return
        lines = ["📋 **Danh sách kênh**"]
        for c in channels:
            lines.append(f"• [{c['channel_type']}] {c['title']} `{c['chat_id']}`")
        await cb.message.answer("\n".join(lines), parse_mode="Markdown")

    @router.callback_query(F.data == "cfg_backup_hours")
    async def cfg_backup(cb: CallbackQuery, state: FSMContext) -> None:
        await cb.answer()
        await state.set_state(ConfigStates.waiting_backup_hours)
        await cb.message.answer("Nhập số giờ giữa các lần backup (vd: 6):")

    @router.message(ConfigStates.waiting_backup_hours)
    async def set_backup_hours(message: Message, state: FSMContext) -> None:
        try:
            h = int(message.text.strip())
            if h < 1:
                raise ValueError
        except ValueError:
            await message.answer("❌ Nhập số giờ hợp lệ")
            return
        await db.set_setting("backup_interval_hours", str(h))
        await state.clear()
        await message.answer(f"✅ Backup mỗi {h} giờ")

    @router.message(F.text == "📁 Mời bot (folder)")
    async def invite_folder(message: Message, state: FSMContext) -> None:
        if not is_admin(message.from_user.id):
            return
        if not userbot_service:
            await message.answer("❌ Userbot chưa chạy")
            return
        await state.set_state(ConfigStates.waiting_folder_name)
        await message.answer(
            "Gửi **tên folder** Telegram (để trống = quét tất cả kênh broadcast):",
            parse_mode="Markdown",
        )

    @router.message(ConfigStates.waiting_folder_name)
    async def do_invite_folder(message: Message, state: FSMContext) -> None:
        folder = message.text.strip()
        me = await message.bot.get_me()
        await db.set_setting("bot_username", me.username or "")
        userbot_service.bot_username = me.username or ""
        result = await userbot_service.invite_bot_to_folder(folder_name=folder)
        await state.clear()
        await message.answer(result[:4000])

    @router.message(F.text == "🔍 Quét duyệt")
    async def scan_approve(message: Message) -> None:
        if not is_admin(message.from_user.id):
            return
        if not userbot_service:
            await message.answer("❌ Userbot chưa chạy")
            return
        result = await userbot_service.scan_pending_and_approve()
        await message.answer(result)

    @router.message(F.text == "💾 Backup ngay")
    async def backup_now(message: Message) -> None:
        if not is_admin(message.from_user.id):
            return
        await message.answer("⏳ Đang tạo backup...")
        await send_backup_to_admins(message.bot, db)
        await message.answer("✅ Đã gửi backup cho admin")

    # --- Broadcast ---
    @router.message(F.text == "📢 Broadcast")
    async def broadcast_start(message: Message, state: FSMContext) -> None:
        if not is_admin(message.from_user.id):
            return
        clear_session(message.from_user.id)
        await state.set_state(BroadcastStates.collecting)
        await message.answer(
            "📢 **Broadcast mode**\n\n"
            "Gửi/chuyển tiếp các bài cần broadcast.\n"
            "Khi xong, bấm **Done** — bot chờ 1s không có tin mới rồi hỏi xác nhận.",
            reply_markup=broadcast_menu(),
            parse_mode="Markdown",
        )

    @router.message(BroadcastStates.collecting, F.text)
    async def broadcast_ignore_text(message: Message) -> None:
        if message.text in ("✅ Done - Gửi broadcast", "❌ Hủy"):
            return
        await message.answer("Chỉ gửi tin nhắn/media để broadcast, hoặc bấm Done.")

    @router.message(BroadcastStates.collecting)
    async def broadcast_collect(message: Message, state: FSMContext) -> None:
        if not is_admin(message.from_user.id):
            return
        session = get_session(message.from_user.id)
        session.add_message(message.chat.id, message.message_id)

        async def ask_confirm() -> None:
            try:
                await message.bot.send_message(
                    message.from_user.id,
                    f"📬 Đã thu {len(session.messages)} bài.\nXác nhận gửi broadcast?",
                    reply_markup=confirm_broadcast(len(session.messages)),
                )
            except Exception as e:
                logger.error("Confirm prompt failed: %s", e)

        session.schedule_idle_check(ask_confirm)
        await message.answer(f"➕ Bài #{len(session.messages)} — gửi thêm hoặc bấm Done")

    @router.callback_query(F.data == "bc_done")
    async def bc_done(cb: CallbackQuery, state: FSMContext) -> None:
        await cb.answer()
        session = get_session(cb.from_user.id)
        if not session.messages:
            await cb.message.answer("❌ Chưa có bài nào")
            return
        session.waiting_confirm = True
        session.cancel_idle()
        await cb.message.answer(
            f"📬 {len(session.messages)} bài — xác nhận gửi?",
            reply_markup=confirm_broadcast(len(session.messages)),
        )

    @router.callback_query(F.data == "bc_cancel")
    async def bc_cancel(cb: CallbackQuery, state: FSMContext) -> None:
        await cb.answer()
        clear_session(cb.from_user.id)
        await state.clear()
        await cb.message.answer("❌ Đã hủy broadcast")

    @router.callback_query(F.data == "bc_confirm")
    async def bc_confirm(cb: CallbackQuery, state: FSMContext) -> None:
        await cb.answer()
        session = get_session(cb.from_user.id)
        if not session.messages:
            await cb.message.answer("❌ Không có bài")
            return

        user_ids = await db.get_all_user_ids()
        if not user_ids:
            user_ids = config.ADMIN_IDS  # fallback test

        sent, failed = 0, 0
        await cb.message.answer(f"🚀 Gửi {len(session.messages)} bài tới {len(user_ids)} user...")

        for uid in user_ids:
            for from_chat, msg_id in session.messages:
                try:
                    await cb.bot.copy_message(chat_id=uid, from_chat_id=from_chat, message_id=msg_id)
                    sent += 1
                except Exception:
                    failed += 1

        clear_session(cb.from_user.id)
        await state.clear()
        await cb.message.answer(f"✅ Broadcast xong\nThành công: {sent}\nLỗi: {failed}")


def create_dispatcher(db: ClenderDB, userbot_service=None) -> Dispatcher:
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    setup_handlers(dp, db, userbot_service)
    return dp
