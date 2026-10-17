import random
import asyncio
from pyrogram import filters, Client
from pyrogram.types import CallbackQuery, InputMediaPhoto, InlineKeyboardMarkup
from pyrogram.enums import ButtonStyle 

import config
from SHIVMUSIC import app, YouTube
from SHIVMUSIC.core.call import ANJALI
from SHIVMUSIC.misc import SUDOERS, db
from SHIVMUSIC.utils.database import (
    get_active_chats, get_lang, get_upvote_count, is_active_chat,
    is_music_playing, is_nonadmin_chat, music_off, music_on, set_loop, get_assistant,
    is_autoplay_on, autoplay_on, autoplay_off
)
from SHIVMUSIC.utils.decorators.language import languageCB
from SHIVMUSIC.utils.formatters import seconds_to_min
from SHIVMUSIC.utils.inline import close_markup, stream_markup, stream_markup_timer, stream_markup2, stream_markup_timer2, panel_markup_1, panel_markup_2, panel_markup_3, panel_markup_4, panel_markup_5
from SHIVMUSIC.utils.stream.autoclear import auto_clean
from SHIVMUSIC.utils.thumbnails import get_thumb
from config import BANNED_USERS, STREAM_IMG_URL, PLAYLIST_IMG_URL, votemode, adminlist
from strings import get_string
from SHIVMUSIC.utils.inline.start import private_panel
from SHIVMUSIC.cplugin.utils.decorators.admins import is_clone_admin

from button import styled_button

checker = {}
upvoters = {}

def get_random_img(img_list):
    if img_list:
        return random.choice(img_list) if isinstance(img_list, list) else img_list
    return "https://telegra.ph/file/2e3d368e77c449c287430.jpg"

@Client.on_callback_query(filters.regex("ADMIN") & ~BANNED_USERS)
@languageCB
async def del_back_playlist(client: Client, CallbackQuery, _):
    bot = await client.get_me()
    callback_data = CallbackQuery.data.strip()
    callback_request = callback_data.split(None, 1)[1]
    command, chat = callback_request.split("|")
    counter = None

    if "_" in str(chat):
        bet = chat.split("_")
        chat, counter = bet[0], bet[1]

    chat_id = int(chat)
    if not await is_active_chat(chat_id):
        return await CallbackQuery.answer(_["general_5"], show_alert=True)

    mention = CallbackQuery.from_user.mention
    user_id = CallbackQuery.from_user.id
    user_name = CallbackQuery.from_user.first_name

    is_non_admin = await is_nonadmin_chat(chat_id)
    if not is_non_admin:
        is_clone_auth = await is_clone_admin(bot.id, CallbackQuery.from_user.id)
        if CallbackQuery.from_user.id not in SUDOERS and not is_clone_auth:
            admins = adminlist.get(chat_id)
            if not admins or CallbackQuery.from_user.id not in admins:
                return await CallbackQuery.answer(_["admin_14"], show_alert=True)

    if command == "UpVote":
        if chat_id not in votemode: votemode[chat_id] = {}
        if chat_id not in upvoters: upvoters[chat_id] = {}

        voters = (upvoters[chat_id]).get(CallbackQuery.message.id, [])
        if CallbackQuery.from_user.id in voters:
            voters.remove(CallbackQuery.from_user.id)
            votemode[chat_id][CallbackQuery.message.id] = max(0, votemode[chat_id].get(CallbackQuery.message.id, 1) - 1)
        else:
            voters.append(CallbackQuery.from_user.id)
            votemode[chat_id][CallbackQuery.message.id] = votemode[chat_id].get(CallbackQuery.message.id, 0) + 1

        upvote = await get_upvote_count(chat_id)
        get_upvotes = votemode[chat_id][CallbackQuery.message.id]

        if get_upvotes >= upvote:
            await CallbackQuery.edit_message_text(_["admin_37"].format(upvote))
        else:
            upl = InlineKeyboardMarkup([[styled_button(text=f"🔥 {get_upvotes}", callback_data=f"ADMIN UpVote|{chat_id}_{counter}", style=ButtonStyle.PRIMARY)]])
            await CallbackQuery.answer(_["admin_40"], show_alert=True)
            await CallbackQuery.edit_message_reply_markup(reply_markup=upl)

    else:
        from SHIVMUSIC.utils.meow import player_action
        await player_action(client, CallbackQuery, _, command, chat_id)


@Client.on_callback_query(filters.regex("^GetTimer$") & ~BANNED_USERS)
async def get_timer_cb(client, CallbackQuery):
    from SHIVMUSIC.utils.meow import progress_bar
    playing = db.get(CallbackQuery.message.chat.id)
    if not playing:
        return await CallbackQuery.answer("ɴσᴛʜɪηɢ ɪs ᴘʟᴧʏɪηɢ.")
    await CallbackQuery.answer(f"⏱ {progress_bar(playing[0].get('played', 0), playing[0].get('dur', '00:00'))}")


# one shared progress-bar updater for main bot + all clones
from SHIVMUSIC.utils.meow import start_refresher
start_refresher()
