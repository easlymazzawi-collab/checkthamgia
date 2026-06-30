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
from bot.approval import scan_and_approve, setup_approval_handlers
from clender.database import ClenderDB
from services.backup import send_backup_to_admins

logger = logging.getLogger(__name__)

router = Router()


class ConfigStates(StatesGroup):
    waiting_folder_name = State()
    waiting_folder_gate = State()
    waiting_invite_folder = State()
    waiting_invite_folder_gate = State()
    waiting_target = State()
    waiting_target_gate = State()
    waiting_backup_hours = State()


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
            "• Mỗi **folder** có 1 kênh gate riêng — member phải vào gate mới duyệt\n"
            "• Bot tự duyệt join request khi vào đúng gate của folder\n"
            "• Userbot chỉ dùng để add bot vào kênh qua folder\n"
            "• Broadcast bằng copy message\n"
            "• Backup tự động theo giờ cấu hình",
            reply_markup=admin_menu(),
        )

    @router.message(F.text == "📊 Thống kê")
    async def stats(message: Message) -> None:
        if not is_admin(message.from_user.id):
            return
        s = await db.stats_summary()
        gates = await db.list_channels("gate")
        folders = await db.list_folders()
        targets = await db.list_channels("target")
        by_ch = await db.stats_by_channel()
        recent = await db.recent_events(15)

        lines = [
            "📊 **Thống kê**",
            f"👥 Tổng user: {s['total_users']}",
            f"🚪 Vào gate: {s['gate_joined']} | ✅ Duyệt: {s['approved']}",
            f"📂 Folder: {len(folders)} | 🔑 Gate: {len(gates)} | 🎯 Kênh đích: {len(targets)}",
            "",
            "**Theo folder:**",
        ]
        for f in folders:
            cnt = len(await db.list_targets_by_folder(f["folder_name"]))
            lines.append(
                f"• 📂 {f['folder_name']} → gate `{f.get('gate_title') or f['gate_channel_id']}` ({cnt} kênh)"
            )
        if by_ch:
            lines.extend(["", "**Theo kênh:**"])
            for row in by_ch[:10]:
                title = row.get("channel_title") or row["channel_id"]
                lines.append(f"• {title} [{row['event_type']}]: {row['cnt']}")
        lines.extend(["", "**Gần đây:**"])
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

    @router.callback_query(F.data == "cfg_folder_gate")
    async def cfg_folder_gate(cb: CallbackQuery, state: FSMContext) -> None:
        await cb.answer()
        await state.set_state(ConfigStates.waiting_folder_name)
        await cb.message.answer(
            "📂 Gửi **tên folder** Telegram.\n"
            "Mỗi folder sẽ có 1 kênh gate riêng — member phải vào gate đó "
            "mới được duyệt các kênh trong folder."
        )

    @router.message(ConfigStates.waiting_folder_name)
    async def set_folder_name(message: Message, state: FSMContext) -> None:
        folder = message.text.strip()
        if not folder:
            await message.answer("❌ Nhập tên folder")
            return
        await state.update_data(folder_name=folder)
        await state.set_state(ConfigStates.waiting_folder_gate)
        existing = await db.get_folder(folder)
        hint = ""
        if existing:
            hint = f"\n(Gate hiện tại: `{existing.get('gate_title') or existing['gate_channel_id']}` — gửi mới để đổi)"
        await message.answer(
            f"Folder: **{folder}**\n"
            f"Gửi @username hoặc chat_id **kênh gate** cho folder này.{hint}",
            parse_mode="Markdown",
        )

    @router.message(ConfigStates.waiting_folder_gate)
    async def set_folder_gate(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        folder = data.get("folder_name", "")
        text = message.text.strip()
        try:
            chat = await message.bot.get_chat(int(text) if text.lstrip("-").isdigit() else text)
        except Exception as e:
            await message.answer(f"❌ Không lấy được kênh gate (bot phải là admin): {e}")
            return

        await db.set_folder_gate(folder, chat.id, chat.title or text)
        updated = await db.apply_folder_gate_to_targets(folder)
        await state.clear()
        await message.answer(
            f"✅ Folder **{folder}**\n"
            f"🔑 Gate: {chat.title} (`{chat.id}`)\n"
            f"🔗 Đã gán gate cho {updated} kênh đích trong folder",
            parse_mode="Markdown",
        )

    @router.callback_query(F.data == "cfg_target_add")
    async def cfg_target(cb: CallbackQuery, state: FSMContext) -> None:
        await cb.answer()
        await state.set_state(ConfigStates.waiting_target)
        await cb.message.answer("Gửi ID hoặc @username **kênh đích** (có bật join request).")

    @router.message(ConfigStates.waiting_target)
    async def set_target(message: Message, state: FSMContext) -> None:
        text = message.text.strip()
        try:
            if text.lstrip("-").isdigit():
                chat = await message.bot.get_chat(int(text))
            else:
                chat = await message.bot.get_chat(text)
        except Exception as e:
            await message.answer(f"❌ Không lấy được kênh (bot phải là admin): {e}")
            return

        await db.add_channel(chat.id, chat.title or text, "target")
        folders = await db.list_folders()
        if len(folders) == 1:
            await db.set_target_gate(chat.id, folders[0]["gate_channel_id"])
            await state.clear()
            await message.answer(
                f"✅ Kênh đích: {chat.title} (`{chat.id}`)\n"
                f"🔗 Gate folder `{folders[0]['folder_name']}`",
                parse_mode="Markdown",
            )
        elif folders:
            await state.update_data(pending_target_id=chat.id, pending_target_title=chat.title)
            await state.set_state(ConfigStates.waiting_target_gate)
            flines = "\n".join(
                f"• {f['folder_name']} → gate `{f.get('gate_title') or f['gate_channel_id']}`"
                for f in folders
            )
            await message.answer(
                f"✅ Kênh đích: {chat.title}\n\nGửi **tên folder** để gán gate:\n{flines}",
                parse_mode="Markdown",
            )
        else:
            await state.clear()
            await message.answer(
                f"✅ Kênh đích: {chat.title} (`{chat.id}`)\n"
                f"⚠️ Chưa có folder/gate — dùng **Set gate cho folder** trước",
                parse_mode="Markdown",
            )

    @router.message(ConfigStates.waiting_target_gate)
    async def set_target_folder_step(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        target_id = data.get("pending_target_id")
        folder_name = message.text.strip()
        folder = await db.get_folder(folder_name)
        if not folder:
            await message.answer("❌ Folder chưa có gate — dùng **Set gate cho folder**")
            return
        await db.set_target_gate(target_id, folder["gate_channel_id"])
        await db.set_channel_folder(target_id, folder_name)
        await state.clear()
        target_title = data.get("pending_target_title", target_id)
        await message.answer(
            f"✅ `{target_title}` → folder `{folder_name}` → gate `{folder.get('gate_title')}`",
            parse_mode="Markdown",
        )

    @router.callback_query(F.data == "cfg_list")
    async def cfg_list(cb: CallbackQuery) -> None:
        await cb.answer()
        folders = await db.list_folders()
        if not folders:
            await cb.message.answer("Chưa có folder nào — dùng **Set gate cho folder**")
            return
        lines = ["📋 **Folder & kênh**"]
        for f in folders:
            targets = await db.list_targets_by_folder(f["folder_name"])
            lines.append(
                f"\n📂 **{f['folder_name']}**"
                f"\n🔑 Gate: {f.get('gate_title') or f['gate_channel_id']} `{f['gate_channel_id']}`"
                f"\n🎯 {len(targets)} kênh đích:"
            )
            for t in targets:
                lines.append(f"  • {t['title']} `{t['chat_id']}`")
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
        await state.set_state(ConfigStates.waiting_invite_folder)
        await message.answer(
            "📂 Gửi **tên folder** Telegram.\n"
            "Userbot sẽ add bot vào các kênh trong folder.\n"
            "Mỗi folder cần 1 kênh gate riêng (sẽ hỏi nếu chưa set).",
            parse_mode="Markdown",
        )

    @router.message(ConfigStates.waiting_invite_folder)
    async def invite_folder_name(message: Message, state: FSMContext) -> None:
        folder = message.text.strip()
        if not folder:
            await message.answer("❌ Nhập tên folder")
            return
        gate_id = await db.get_folder_gate(folder)
        if gate_id:
            await _run_invite(message, state, userbot_service, db, folder, gate_id)
        else:
            await state.update_data(invite_folder=folder)
            await state.set_state(ConfigStates.waiting_invite_folder_gate)
            await message.answer(
                f"Folder **{folder}** chưa có gate.\n"
                f"Gửi @username hoặc chat_id **kênh gate** cho folder này:",
                parse_mode="Markdown",
            )

    @router.message(ConfigStates.waiting_invite_folder_gate)
    async def invite_folder_gate(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        folder = data.get("invite_folder", "")
        text = message.text.strip()
        try:
            chat = await message.bot.get_chat(int(text) if text.lstrip("-").isdigit() else text)
        except Exception as e:
            await message.answer(f"❌ {e}")
            return
        await db.set_folder_gate(folder, chat.id, chat.title or text)
        await _run_invite(message, state, userbot_service, db, folder, chat.id)

    async def _run_invite(message, state, userbot_service, db, folder, gate_id):
        me = await message.bot.get_me()
        await db.set_setting("bot_username", me.username or "")
        userbot_service.bot_username = me.username or ""
        result = await userbot_service.invite_bot_to_folder(folder, gate_id)
        await state.clear()
        await message.answer(result[:4000], parse_mode="Markdown")

    @router.message(F.text == "🔍 Quét duyệt")
    async def scan_approve(message: Message) -> None:
        if not is_admin(message.from_user.id):
            return
        result = await scan_and_approve(message.bot, db)
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
    setup_approval_handlers(dp, db)
    setup_handlers(dp, db, userbot_service)
    return dp
