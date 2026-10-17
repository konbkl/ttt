"""Meow-style UI kit shared by the main bot and every clone.

    from SHIVMUSIC.utils.meow import fancy, btn, rows_to_kb, player_markup, quote

* fancy()          -> small-caps font (ᴧ є σ η ...) that keeps HTML, links,
                      {placeholders}, /commands and @mentions untouched
* btn()            -> InlineKeyboardButton with a random colour (blue/green/red)
* player_markup()  -> now-playing keyboard (progress bar, ▷ II ↻ ‣‣I ▢,
                      -15s / repo / 15s+, autoplay toggle, close)
* thumbnails on/off per chat (/nothumb)
"""

import random
import re

from pyrogram.enums import ButtonStyle
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import config

# ------------------------------------------------------------------ colours
STYLES = (ButtonStyle.PRIMARY, ButtonStyle.SUCCESS, ButtonStyle.DANGER)


def rstyle():
    return random.choice(STYLES)


from meowfont import fancy, quote, nice_duration, player_caption, _to_sec, _fmt  # noqa: F401


# ------------------------------------------------------------------ buttons
def btn(text, cb=None, url=None, user_id=None, style=None, font=True, **extra):
    kw = {"text": fancy(text) if font else str(text), "style": style or rstyle()}
    if url:
        kw["url"] = url
    elif user_id:
        kw["user_id"] = int(user_id)
    else:
        kw["callback_data"] = cb or "meow_none"
    # premium icons only when explicitly enabled (they fail for normal bots)
    icon = extra.pop("icon_custom_emoji_id", None)
    if icon and getattr(config, "BUTTON_ICONS", False):
        kw["icon_custom_emoji_id"] = str(icon)
    return InlineKeyboardButton(**kw)


def rows_to_kb(rows):
    return InlineKeyboardMarkup(rows)


def tg_link(val, fallback=None):
    """'@chat', 'chat', 't.me/chat' or full url -> https url."""
    if not val or str(val).strip().lower() in ("", "none"):
        return fallback or config.SUPPORT_CHAT
    val = str(val).strip()
    if " " in val:  # e.g. "No support chat set."
        return fallback or config.SUPPORT_CHAT
    if val.startswith(("https://", "http://", "tg://")):
        return val
    if val.startswith("t.me/"):
        return "https://" + val
    return f"https://t.me/{val.lstrip('@')}"


# ------------------------------------------------------------------ player
SEEK_STEP = 15


def progress_bar(played, dur, size=9):
    p, d = _to_sec(played), _to_sec(dur)
    pos = min(size, int(size * p / d)) if d else 0
    line = "—" * pos + "●" + "—" * (size - pos)
    return f"{_fmt(p)} {line} {_fmt(d) if d else dur}"


def _autoplay_state(chat_id):
    try:
        from SHIVMUSIC.utils.database.database import autoplay
        return bool(autoplay.get(int(chat_id), False))
    except Exception:
        return False


def _now(chat_id):
    try:
        from SHIVMUSIC.misc import db
        q = db.get(int(chat_id))
        if q:
            return q[0].get("played", 0), q[0].get("dur", "00:00")
    except Exception:
        pass
    return 0, "00:00"


def repo_url():
    return getattr(config, "REPO_URL", None) or config.SUPPORT_CHANNEL


def player_markup(_=None, chat_id=0, played=None, dur=None, **__):
    """Returns a list of rows (callers wrap it in InlineKeyboardMarkup)."""
    if played is None or dur is None:
        p, d = _now(chat_id)
        played = p if played is None else played
        dur = d if dur is None else dur
    rows = []
    if _to_sec(dur):
        rows.append([btn(progress_bar(played, dur), cb="GetTimer", font=False)])
    rows.append([
        btn("▷", cb=f"ADMIN Resume|{chat_id}", font=False),
        btn("II", cb=f"ADMIN Pause|{chat_id}", font=False),
        btn("↻", cb=f"ADMIN Replay|{chat_id}", font=False),
        btn("‣‣I", cb=f"ADMIN Skip|{chat_id}", font=False),
        btn("▢", cb=f"ADMIN Stop|{chat_id}", font=False),
    ])
    rows.append([
        btn(f"-{SEEK_STEP}ˢ", cb=f"ADMIN SeekBack|{chat_id}", font=False),
        btn("Repo", url=repo_url()),
        btn(f"{SEEK_STEP}ˢ+", cb=f"ADMIN SeekForward|{chat_id}", font=False),
    ])
    state = "Enabled" if _autoplay_state(chat_id) else "Disabled"
    rows.append([btn(f"♫ Autoplay: {state}", cb=f"ADMIN Autoplay|{chat_id}")])
    rows.append([btn("Close", cb="close")])
    return rows


# ------------------------------------------------------------------ seek / replay
async def seek_player(chat_id, delta=None, to=None):
    """Seek the running stream. Returns (ok, text)."""
    from SHIVMUSIC import YouTube
    from SHIVMUSIC.core.call import ANJALI
    from SHIVMUSIC.misc import db

    playing = db.get(chat_id)
    if not playing:
        return False, fancy("Nothing is playing.")
    total = int(playing[0].get("seconds", 0) or 0)
    played = int(playing[0].get("played", 0) or 0)
    if total == 0:
        return False, fancy("Can't seek a live stream.")
    target = to if to is not None else played + delta
    target = max(0, min(target, total - 3))
    file_path = playing[0].get("file", "")
    if playing[0].get("speed_path"):
        file_path = playing[0]["speed_path"]
    elif "vid_" in file_path:
        n, file_path = await YouTube.video(playing[0]["vidid"], True)
        if n == 0:
            return False, fancy("Seek failed, try again.")
    elif "index_" in file_path:
        file_path = playing[0]["vidid"]
    try:
        await ANJALI.seek_stream(chat_id, file_path, _fmt(target),
                                 playing[0].get("dur", "00:00"),
                                 playing[0].get("streamtype", "audio"))
    except Exception:
        return False, fancy("Seek failed, try again.")
    if db.get(chat_id):
        db[chat_id][0]["played"] = target
    return True, f"⏱ {_fmt(target)} / {playing[0].get('dur', '')}"


# ------------------------------------------------------------------ thumbnail on/off
_thumb_cache = {}


def _thumbdb():
    from SHIVMUSIC.core.mongo import mongodb
    return mongodb.thumbmode


async def is_thumb_on(chat_id) -> bool:
    chat_id = int(chat_id)
    if chat_id not in _thumb_cache:
        try:
            doc = await _thumbdb().find_one({"chat_id": chat_id})
            _thumb_cache[chat_id] = not bool(doc and doc.get("off"))
        except Exception:
            _thumb_cache[chat_id] = True
    return _thumb_cache[chat_id]


async def set_thumb(chat_id, on: bool):
    chat_id = int(chat_id)
    _thumb_cache[chat_id] = on
    try:
        if on:
            await _thumbdb().delete_one({"chat_id": chat_id})
        else:
            await _thumbdb().update_one({"chat_id": chat_id}, {"$set": {"off": True}}, upsert=True)
    except Exception:
        pass


async def send_card(client, chat_id=None, photo=None, caption="", reply_markup=None, **kw):
    """Drop-in for client.send_photo() on now-playing cards.
    Respects /nothumb and falls back to a text message if the photo fails."""
    kw.pop("has_spoiler", None)
    if isinstance(photo, (list, tuple)):
        photo = random.choice(photo) if photo else None
    if photo and await is_thumb_on(chat_id):
        try:
            return await client.send_photo(chat_id, photo=photo, caption=caption,
                                           reply_markup=reply_markup, **kw)
        except Exception as e:
            print(f"[MEOW] photo card failed, sending text: {e}")
    return await client.send_message(chat_id, caption, reply_markup=reply_markup,
                                     disable_web_page_preview=True)


send_player = send_card


# ------------------------------------------------------------------ player buttons
async def player_action(client, cq, _, command, chat_id):
    """Handles the Meow player buttons (permission checks are done by the caller).
    Returns True when the command was handled here."""
    from SHIVMUSIC.core.call import ANJALI
    from SHIVMUSIC.misc import db
    from SHIVMUSIC.utils.database import (
        autoplay_off, autoplay_on, is_autoplay_on, is_music_playing,
        music_off, music_on, set_loop,
    )

    mention = cq.from_user.mention

    async def refresh():
        try:
            await cq.edit_message_reply_markup(InlineKeyboardMarkup(player_markup(_, chat_id)))
        except Exception:
            pass

    if command == "Pause":
        if not await is_music_playing(chat_id):
            return await cq.answer(fancy("Stream is already paused."), show_alert=True) or True
        await ANJALI.pause_stream(chat_id)
        await music_off(chat_id)
        await cq.answer(fancy("Stream paused ⏸"))
        try:
            await cq.message.reply_text(_["admin_2"].format(mention))
        except Exception:
            pass
        return True

    if command == "Resume":
        if await is_music_playing(chat_id):
            return await cq.answer(fancy("Stream is already playing."), show_alert=True) or True
        await ANJALI.resume_stream(chat_id)
        await music_on(chat_id)
        await cq.answer(fancy("Stream resumed ▶️"))
        try:
            await cq.message.reply_text(_["admin_4"].format(mention))
        except Exception:
            pass
        return True

    if command in ("Stop", "End"):
        await cq.answer(fancy("Stream stopped."))
        await ANJALI.stop_stream(chat_id)
        await set_loop(chat_id, 0)
        try:
            await cq.message.reply_text(_["admin_5"].format(mention))
            await cq.message.delete()
        except Exception:
            pass
        return True

    if command == "Autoplay":
        if await is_autoplay_on(chat_id):
            await autoplay_off(chat_id)
            await cq.answer(fancy("Autoplay disabled"), show_alert=False)
        else:
            await autoplay_on(chat_id)
            await cq.answer(fancy("Autoplay enabled"), show_alert=False)
        await refresh()
        return True

    if command in ("SeekBack", "SeekForward", "1", "2"):
        delta = -SEEK_STEP if command in ("SeekBack", "1") else SEEK_STEP
        ok, text = await seek_player(chat_id, delta=delta)
        await cq.answer(text, show_alert=not ok)
        if ok:
            await refresh()
        return True

    if command == "Replay":
        ok, text = await seek_player(chat_id, to=0)
        await cq.answer(fancy("Replaying from start ↻") if ok else text, show_alert=not ok)
        if ok:
            await refresh()
        return True

    if command == "Skip":
        if not db.get(chat_id):
            return await cq.answer(fancy("Queue is empty."), show_alert=True) or True
        await cq.answer(fancy("Skipped ‣‣I"))
        await set_loop(chat_id, 0)
        try:
            await cq.message.delete()
        except Exception:
            pass
        clients = await ANJALI.get_active_clients(chat_id)
        await ANJALI.change_stream(clients[0] if clients else ANJALI.one, chat_id)
        return True

    try:
        await cq.answer()
    except Exception:
        pass
    return False


# ------------------------------------------------------------------ live progress updater
_last = {}


async def refresh_players():
    """One loop for main + clones: keeps the progress bar / autoplay label fresh."""
    import asyncio
    from pyrogram.errors import FloodWait
    from SHIVMUSIC.misc import db
    from SHIVMUSIC.utils.database import get_active_chats, is_music_playing

    while True:
        await asyncio.sleep(10)
        try:
            chats = await get_active_chats()
        except Exception:
            continue
        for chat_id in chats:
            try:
                if not await is_music_playing(chat_id):
                    continue
                q = db.get(chat_id)
                if not q or not int(q[0].get("seconds", 0) or 0):
                    continue
                mystic = q[0].get("mystic")
                if not mystic:
                    continue
                key = (mystic.chat.id, mystic.id)
                stamp = (int(q[0].get("played", 0)) // 10, _autoplay_state(chat_id))
                if _last.get(key) == stamp:
                    continue
                _last[key] = stamp
                await mystic.edit_reply_markup(InlineKeyboardMarkup(player_markup(None, chat_id)))
            except FloodWait as e:
                await asyncio.sleep(min(int(e.value), 30))
            except Exception:
                continue
        if len(_last) > 2000:
            _last.clear()


_started = False


def start_refresher():
    global _started
    if _started:
        return
    _started = True
    import asyncio
    try:
        asyncio.get_event_loop().create_task(refresh_players())
    except Exception:
        _started = False


# ------------------------------------------------------------------ help menu
CLONE_HIDDEN = ("restrict",)  # these commands only exist on the main bot


def help_markup(is_clone=False, show_clone_settings=False, back_cb=None):
    from strings.meowhelp import SECTIONS

    keys = [k for k in SECTIONS if not (is_clone and k in CLONE_HIDDEN)]
    rows, row = [], []
    for k in keys:
        row.append(btn(SECTIONS[k][0], cb=f"meowhelp {k}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    if is_clone:
        if show_clone_settings:
            rows.append([btn("⚙️ Clone Settings", cb="meowhelp csettings")])
    else:
        rows.append([btn("Clone Feature", cb="meowhelp clonefeat")])
    rows.append([btn("⟵", cb=back_cb or ("settingsback_home" if is_clone else "meow_home"), font=False)])
    return InlineKeyboardMarkup(rows)


def back_markup(cb="meowhelp home"):
    return InlineKeyboardMarkup([[btn("⟵", cb=cb, font=False)]])


def clone_settings_markup():
    from strings.meowhelp import CLONE_SETTINGS

    keys = list(CLONE_SETTINGS)
    rows = []
    for i in range(0, len(keys), 2):
        rows.append([btn(CLONE_SETTINGS[k][0], cb=f"meowhelp {k}") for k in keys[i:i + 2]])
    rows.append([btn("⟵", cb="meowhelp home", font=False)])
    return InlineKeyboardMarkup(rows)


async def meow_edit(cq, text, markup):
    """Edit a menu message whether it is a photo/video (caption) or plain text."""
    from pyrogram.errors import MessageNotModified

    m = cq.message
    try:
        if m.photo or m.video or m.animation or m.document:
            await cq.edit_message_caption(text, reply_markup=markup)
        else:
            await cq.edit_message_text(text, reply_markup=markup, disable_web_page_preview=True)
    except MessageNotModified:
        pass


async def help_router(client, cq, key, is_clone, is_owner, support_link):
    """Shared handler for 'meowhelp <key>' callbacks."""
    from strings.meowhelp import (CLONE_FEATURE, CLONE_SETTINGS,
                                  CLONE_SETTINGS_HOME, HELP_HOME, SECTIONS)
    try:
        await cq.answer()
    except Exception:
        pass
    if key == "home":
        return await meow_edit(cq, HELP_HOME.format(support_link),
                               help_markup(is_clone, is_owner))
    if key in SECTIONS:
        return await meow_edit(cq, SECTIONS[key][1], back_markup())
    if key == "clonefeat" and not is_clone:
        return await meow_edit(cq, CLONE_FEATURE, back_markup())
    if key == "csettings" and is_clone:
        if not is_owner:
            return await cq.answer(fancy("Only the bot owner can open this."), show_alert=True)
        return await meow_edit(cq, CLONE_SETTINGS_HOME, clone_settings_markup())
    if key in CLONE_SETTINGS and is_clone:
        if not is_owner:
            return await cq.answer(fancy("Only the bot owner can open this."), show_alert=True)
        return await meow_edit(cq, CLONE_SETTINGS[key][1], back_markup("meowhelp csettings"))


# ------------------------------------------------------------------ start buttons
def main_start_markup(bot_username):
    return InlineKeyboardMarkup([
        [btn("✧₊ Add me to your chat ₊✧", url=f"https://t.me/{bot_username}?startgroup=true")],
        [btn("Help & Commands", cb="settings_back_helper")],
        [btn("Updates", url=config.SUPPORT_CHANNEL), btn("Support", url=config.SUPPORT_CHAT)],
        [btn("How to clone", cb="meowhelp clonefeat")],
    ])


def thumb_markup(chat_id):
    return InlineKeyboardMarkup([
        [btn("Enable", cb=f"meowthumb on|{chat_id}"), btn("Disable", cb=f"meowthumb off|{chat_id}")],
        [btn("Close", cb="close")],
    ])


def thumb_text(on: bool):
    state = fancy("Enabled") if on else fancy("Disabled")
    return (
        f"⦿ <b><u>{fancy('Thumbnail settings')} :</u></b>\n\n"
        f"<blockquote>🎨 <b>{fancy('Album art display')} :</b> {state}</blockquote>\n"
        f"<blockquote expandable>• <b>{fancy('Enable')}</b> : {fancy('display artwork with stream info.')}\n"
        f"• <b>{fancy('Disable')}</b> : {fancy('send pure text-based updates.')}\n"
        f"• <b>{fancy('Close')}</b> : {fancy('dismiss the configuration.')}\n\n"
        f"❏ {fancy('Settings are saved individually per chat.')}</blockquote>"
    )


# ------------------------------------------------------------------ clone owner filter
async def _clone_owner_check(_, client, update):
    user = getattr(update, "from_user", None)
    if not user:
        return False
    if user.id == config.OWNER_ID:
        return True
    try:
        from SHIVMUSIC.utils.database.clonedb import get_owner_id_from_db
        me = client.me or await client.get_me()
        return user.id == await get_owner_id_from_db(me.id)
    except Exception:
        return False


def _make_owner_filter():
    from pyrogram import filters as _f
    return _f.create(_clone_owner_check, "CloneOwner")


clone_owner = _make_owner_filter()
