import asyncio
import logging
from typing import Set, Dict
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatMemberStatus
import html
from pytgcalls.types import UpdatedGroupCallParticipant, GroupCallParticipant
from pytgcalls import filters as fl

from SHIVMUSIC import app, userbot
from SHIVMUSIC.core.call import ANJALI 
from SHIVMUSIC.misc import SUDOERS
from config import adminlist

logger = logging.getLogger(__name__)

enabled_chats: Dict[int, Client] = {}   # chat_id -> bot that enabled the logger
user_join_count: Dict[tuple, int] = {}
user_cache: Dict[int, tuple] = {}
vc_participants_cache: Dict[int, list] = {}
DELETE_DELAY = 7


def _bot_for(chat_id: int):
    return enabled_chats.get(chat_id) or app


async def delete_message_after_delay(bot, chat_id: int, message_id: int):
    try:
        await asyncio.sleep(DELETE_DELAY)
        await bot.delete_messages(chat_id, message_id)
    except Exception:
        pass


async def get_user_info(chat_id: int, user_id: int) -> tuple:
    if user_id in user_cache:
        return user_cache[user_id]
    name, username = None, "ɴσηє"
    try:
        member = await _bot_for(chat_id).get_chat_member(chat_id, user_id)
        if member and member.user:
            user = member.user
            name = user.first_name or ""
            if user.last_name:
                name += f" {user.last_name}"
            username = f"@{user.username}" if user.username else "ɴσηє"
    except Exception:
        pass
    user_cache[user_id] = (name, username)
    return name, username


async def _total_vc(chat_id: int):
    try:
        return len(await ANJALI.one.get_participants(chat_id))
    except Exception:
        return None


async def _send_vc_log(chat_id: int, user_id: int, joined: bool):
    bot = _bot_for(chat_id)
    name, username = await get_user_info(chat_id, user_id)
    mention = f'<a href="tg://user?id={user_id}">{html.escape(name or "User")}</a>'
    tag = "#JσɪηVɪᴅєσCʜᴧᴛ" if joined else "#ʟєᴧᴠєVɪᴅєσCʜᴧᴛ"
    dot = "🟢" if joined else "🔴"
    body = (
        f"<b>ɴᴧᴍє ➛</b> {mention}\n"
        f"<b>ɪᴅ ➛</b> <code>{user_id}</code>\n"
        f"<b>ᴜsєʀηᴧᴍє ➛</b> {username}"
    )
    total = await _total_vc(chat_id)
    if total is not None:
        body += f"\n<b>👥 ᴛσᴛᴧʟ ᴠᴄ ➛</b> {total}"
    if joined:
        key = (chat_id, user_id)
        user_join_count[key] = user_join_count.get(key, 0) + 1
        if user_join_count[key] > 1:
            body += f"\n<b>🔁 ᴊσɪη ᴄσᴜηᴛ ➛</b> {user_join_count[key]}"
    text = f"{dot} <b>{tag}</b>\n<blockquote>{body}</blockquote>"
    try:
        msg = await bot.send_message(chat_id, text)
        asyncio.create_task(delete_message_after_delay(bot, chat_id, msg.id))
    except Exception as e:
        logger.debug(f"vc log failed: {e}")


async def send_join_notification(chat_id: int, user_id: int):
    await _send_vc_log(chat_id, user_id, True)


async def send_leave_notification(chat_id: int, user_id: int):
    await _send_vc_log(chat_id, user_id, False)


async def is_admin(client, chat_id: int, user_id: int) -> bool:
    try:
        if user_id in SUDOERS:
            return True
        admins = adminlist.get(chat_id)
        if admins and user_id in admins:
            return True
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except Exception:
        return False

@ANJALI.one.on_update(fl.call_participant(GroupCallParticipant.Action.JOINED))
async def participant_join(_, update: UpdatedGroupCallParticipant):
    chat_id = update.chat_id
    user_id = update.participant.user_id

    if chat_id not in enabled_chats:
        return

    await send_join_notification(chat_id, user_id)

@ANJALI.one.on_update(fl.call_participant(GroupCallParticipant.Action.LEFT))
async def participant_left(_, update: UpdatedGroupCallParticipant):
    chat_id = update.chat_id
    user_id = update.participant.user_id

    if chat_id not in enabled_chats:
        return

    await send_leave_notification(chat_id, user_id)

@Client.on_message(filters.command(["vclogger", "vclog"]) & filters.group)
async def vclogger_cmd(client: Client, message: Message):
    chat_id = message.chat.id

    if message.from_user and not await is_admin(client, chat_id, message.from_user.id):
        return await message.reply_text("**❌ ᴀᴅᴍɪɴ ᴏɴʟʏ!**")

    if len(message.command) < 2:
        status = chat_id in enabled_chats
        await message.reply_text(
            f"<blockquote><b>📊 ᴠᴄ ʟσɢɢєʀ :</b> {'✅ ση' if status else '❌ σғғ'}</blockquote>\n"
            "<blockquote expandable><b>➻ /vclogger on</b> : ᴇηᴧʙʟє\n<b>➻ /vclogger off</b> : ᴅɪsᴧʙʟє</blockquote>"
        )
        return

    action = message.command[1].lower()

    if action == "on":
        enabled_chats[chat_id] = client
        await message.reply_text("<blockquote><b>✅ ᴠᴄ ʟσɢɢєʀ єηᴧʙʟєᴅ!</b></blockquote>")

    elif action == "off":
        enabled_chats.pop(chat_id, None)
        user_join_count.clear()
        await message.reply_text("<blockquote><b>❌ ᴠᴄ ʟσɢɢєʀ ᴅɪsᴧʙʟєᴅ!</b></blockquote>")

    else:
        await message.reply_text("**ᴜsᴇ:** /vclogger on | off")
        
