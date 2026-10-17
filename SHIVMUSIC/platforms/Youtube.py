import asyncio
import os
import re
import time
import yt_dlp
import aiohttp
import logging
import config  
from typing import Union
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from youtubesearchpython.__future__ import VideosSearch, Playlist

# ----------------- CONFIGURATION -----------------
DOWNLOAD_DIR = "downloads"
LOGGER = logging.getLogger(__name__)

# 🟢 Primary API (Shruti - Promoted after removing Inflex)
SHRUTI_API_URL = os.environ.get("SHRUTI_API_URL", "https://shrutibots.site")
SHRUTI_API_KEY = os.environ.get("SHRUTI_API_KEY", "")

def time_to_seconds(time_str):
    stringt = str(time_str)
    return sum(int(x) * 60 ** i for i, x in enumerate(reversed(stringt.split(":"))))

def get_safe_filename(title: str, default_id: str) -> str:
    if not title:
        return default_id
    return re.sub(r'[\\/*?:"<>|]', "", title).strip()

def extract_video_id(link: str) -> str:
    if "youtu.be/" in link:
        return link.split("youtu.be/")[1].split("?")[0]
    elif "v=" in link:
        return link.split("v=")[1].split("&")[0]
    return link

# Helper for Safe Async Execution
async def _async_run(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))

# ----------------- DOWNLOADER (ONLY SHRUTI API) -----------------
# SHRUTI_STREAM=True  -> VC turant start: API ka link seedha ffmpeg ko (download ka wait nahi)
# SHRUTI_STREAM=False -> pehle pura file download, phir play (purana tareeka)
SHRUTI_STREAM = os.environ.get("SHRUTI_STREAM", "True").lower() in ("true", "1", "yes", "on")


def _shruti_params(video_id: str, download_type: str) -> dict:
    return {
        "url": video_id,
        "type": "video" if download_type == "video" else "audio",
        "api_key": SHRUTI_API_KEY,
    }


def _cached_file(video_id: str, download_type: str):
    ext = "mp4" if download_type == "video" else "mp3"
    path = os.path.join(DOWNLOAD_DIR, f"Shr_{video_id}.{ext}")
    if os.path.exists(path) and os.path.getsize(path) > 50000:
        return path
    return None


def shruti_stream_url(video_id: str, download_type: str = "audio") -> str:
    """Direct API link, ffmpeg isko seedha stream karta hai (2-3 sec me VC)."""
    from urllib.parse import urlencode
    return f"{SHRUTI_API_URL}/download?{urlencode(_shruti_params(video_id, download_type))}"


async def shruti_download(video_id: str, download_type: str = "audio") -> str:
    """Pura file download (sirf SHRUTI_STREAM=False ho tab)."""
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    cached = _cached_file(video_id, download_type)
    if cached:
        return cached
    ext = "mp4" if download_type == "video" else "mp3"
    file_path = os.path.join(DOWNLOAD_DIR, f"Shr_{video_id}.{ext}")
    tmp_path = file_path + ".part"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{SHRUTI_API_URL}/download",
                params=_shruti_params(video_id, download_type),
                timeout=aiohttp.ClientTimeout(total=600),
            ) as resp:
                if resp.status != 200:
                    LOGGER.error(f"🔴 Shruti Error: Status {resp.status}")
                    return None
                with open(tmp_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(131072):
                        f.write(chunk)
        if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 50000:
            os.replace(tmp_path, file_path)
            return file_path
        LOGGER.warning(f"🔴 Shruti returned empty file for {video_id}")
    except Exception as e:
        LOGGER.error(f"Shruti Download Error: {e}")
    try:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    except Exception:
        pass
    return None


async def get_media(link: str, download_type: str = "audio") -> str:
    """Sirf Shruti API. Pehle se downloaded file ho to wahi, warna stream link / download."""
    video_id = extract_video_id(link)
    if not video_id or len(video_id) < 3:
        return None
    if not SHRUTI_API_URL or not SHRUTI_API_KEY:
        LOGGER.error("🔴 SHRUTI_API_KEY set nahi hai! .env / Railway variables me daalo.")
        return None
    cached = _cached_file(video_id, download_type)
    if cached:
        return cached
    if SHRUTI_STREAM:
        return shruti_stream_url(video_id, download_type)
    return await shruti_download(video_id, download_type)


async def download_song(link: str, title: str = None) -> str:
    return await get_media(link, "audio")


async def download_video(link: str, title: str = None) -> str:
    return await get_media(link, "video")


# ----------------- YOUTUBE API CLASS -----------------

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.status = "https://www.youtube.com/oembed?url="
        self.listbase = "https://youtube.com/playlist?list="
        self.reg = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        return bool(re.search(self.regex, link))

    async def url(self, message_1: Message) -> Union[str, None]:
        messages = [message_1]
        if message_1.reply_to_message:
            messages.append(message_1.reply_to_message)
        for message in messages:
            if message.entities:
                for entity in message.entities:
                    if entity.type == MessageEntityType.URL:
                        text = message.text or message.caption
                        return text[entity.offset: entity.offset + entity.length]
            elif message.caption_entities:
                for entity in message.caption_entities:
                    if entity.type == MessageEntityType.TEXT_LINK:
                        return entity.url
        return None

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]

        try:
            results = VideosSearch(link, limit=1)
            response = await results.next()
            if response and response.get("result"):
                for result in response["result"]:
                    title = result["title"]
                    duration_min = result["duration"]
                    thumbnail = result["thumbnails"][0]["url"].split("?")[0]
                    vidid = result["id"]
                    duration_sec = int(time_to_seconds(duration_min)) if duration_min else 0
                    return title, duration_min, duration_sec, thumbnail, vidid
        except Exception:
            pass

        try:
            # Removed cookies.txt
            ydl_opts = {
                "quiet": True, 
                "extract_flat": True, 
                "noplaylist": True,
                "extractor_args": {"youtube": ["player_client=ios,tv_embedded"]} 
            } 
            ydl = yt_dlp.YoutubeDL(ydl_opts)
            search_query = link if "youtube.com" in link or "youtu.be" in link else f"ytsearch1:{link}"

            r = await _async_run(ydl.extract_info, search_query, download=False)
            if r and "entries" in r and len(r["entries"]) > 0:
                entry = r["entries"][0]
                title = entry.get("title")
                vidid = entry.get("id")
                dur_sec = int(entry.get("duration", 0))
                m, s = divmod(dur_sec, 60)
                h, m = divmod(m, 60)
                duration_min = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
                thumbnail = f"https://img.youtube.com/vi/{vidid}/hqdefault.jpg"
                return title, duration_min, dur_sec, thumbnail, vidid
        except Exception as e:
            LOGGER.error(f"yt-dlp search fallback failed in details: {e}")
        return None, None, None, None, None

    async def title(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]
        try:
            results = VideosSearch(link, limit=1)
            for result in (await results.next())["result"]:
                return result["title"]
        except Exception:
            return "Unknown Title"

    async def duration(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]
        try:
            results = VideosSearch(link, limit=1)
            for result in (await results.next())["result"]:
                return result["duration"]
        except Exception:
            return "0:00"

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        # Capturing raw video id to prevent missing thumbs on clone bots
        vid_id_str = link if videoid else extract_video_id(link)
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]
        try:
            results = VideosSearch(link, limit=1)
            for result in (await results.next())["result"]:
                return result["thumbnails"][0]["url"].split("?")[0]
        except Exception:
            # Replaced hardcoded telegra.ph broken thumbnail with a dynamic YouTube one
            if vid_id_str and len(vid_id_str) > 5:
                return f"https://img.youtube.com/vi/{vid_id_str}/hqdefault.jpg"
            return "https://telegra.ph/file/2e3d368e77c449c287430.jpg"

    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]
        try:
            downloaded_file = await download_video(link)
            if downloaded_file:
                return 1, downloaded_file
            return 0, "Video download failed"
        except Exception as e:
            return 0, f"Video download error: {e}"

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid: link = self.listbase + link
        if "&" in link: link = link.split("&")[0]
        try:
            plist = await _async_run(Playlist.get, link)
        except Exception:
            return []
        videos = plist.get("videos") or []
        ids = []
        for data in videos[:limit]:
            if not data: continue
            vid = data.get("id")
            if not vid: continue
            ids.append(vid)
        return ids

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]

        try:
            results = VideosSearch(link, limit=1)
            response = await results.next()
            if response and response.get("result"):
                result = response["result"][0]
                return {
                    "title": result["title"],
                    "link": result["link"],
                    "vidid": result["id"],
                    "duration_min": result["duration"],
                    "thumb": result["thumbnails"][0]["url"].split("?")[0],
                }, result["id"]
        except Exception:
            pass

        try:
            # Removed cookies.txt
            ydl_opts = {
                "quiet": True, 
                "extract_flat": True, 
                "noplaylist": True,
                "extractor_args": {"youtube": ["player_client=ios,tv_embedded"]} 
            }
            ydl = yt_dlp.YoutubeDL(ydl_opts)
            search_query = link if "youtube.com" in link or "youtu.be" in link else f"ytsearch1:{link}"
            r = await _async_run(ydl.extract_info, search_query, download=False)

            if r and "entries" in r and len(r["entries"]) > 0:
                entry = r["entries"][0]
                vidid = entry.get("id")
                dur_sec = int(entry.get("duration", 0))
                m, s = divmod(dur_sec, 60)
                h, m = divmod(m, 60)

                return {
                    "title": entry.get("title"),
                    "link": f"https://www.youtube.com/watch?v={vidid}",
                    "vidid": vidid,
                    "duration_min": f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}",
                    "thumb": f"https://img.youtube.com/vi/{vidid}/hqdefault.jpg",
                }, vidid
        except Exception as e:
            LOGGER.error(f"yt-dlp search fallback failed in track: {e}")

        return None, None

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]

        # Removed cookies.txt
        ytdl_opts = {
            "quiet": True,
            "extractor_args": {"youtube": ["player_client=ios,tv_embedded"]},
            "external_downloader": "aria2c",
            "external_downloader_args": [
                "-x", "16",            
                "-s", "16",            
                "-k", "1M",            
                "--allow-piece-length-change=true"
            ]
        }

        ydl = yt_dlp.YoutubeDL(ytdl_opts)
        formats_available = []

        try:
            r = await _async_run(ydl.extract_info, link, download=False)
            if r and "formats" in r:
                for format in r["formats"]:
                    try:
                        if "dash" not in str(format.get("format", "")).lower():
                            formats_available.append({
                                "format": format.get("format"),
                                "filesize": format.get("filesize"),
                                "format_id": format.get("format_id"),
                                "ext": format.get("ext"),
                                "format_note": format.get("format_note"),
                                "yturl": link,
                            })
                    except Exception: continue
        except Exception:
            pass

        return formats_available, link

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        raw_vid_str = link if videoid else extract_video_id(link)
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]

        try:
            a = VideosSearch(link, limit=10)
            result = (await a.next()).get("result")
            return result[query_type]["title"], result[query_type]["duration"], result[query_type]["thumbnails"][0]["url"].split("?")[0], result[query_type]["id"]
        except Exception:
            # Clone bot fallback fix
            fallback_thumb = f"https://img.youtube.com/vi/{raw_vid_str}/hqdefault.jpg" if raw_vid_str and len(raw_vid_str) > 5 else "https://telegra.ph/file/2e3d368e77c449c287430.jpg"
            return "Unknown Title", "0:00", fallback_thumb, "None"

    async def download(
        self, link: str, mystic, video: Union[bool, str] = None, videoid: Union[bool, str] = None,
        songaudio: Union[bool, str] = None, songvideo: Union[bool, str] = None, format_id: Union[bool, str] = None,
        title: Union[bool, str] = None,
    ) -> str:
        if videoid: link = self.base + link
        try:
            if video: downloaded_file = await download_video(link)
            else: downloaded_file = await download_song(link)

            if downloaded_file: return downloaded_file, True
            return None, False
        except Exception as e:
            LOGGER.error(f"Error in YouTubeAPI.download: {e}")
            return None, False

    async def autoplay(self, last_vidid: str, title: str, max_duration: int = None):
        try:
            import random
            search_query = f"{title} official audio"
            valid_choices = []

            try:
                search = VideosSearch(search_query, limit=15)
                result = await search.next()
                if result and result.get("result"):
                    for res in result["result"]:
                        vidid = str(res.get("id") or "")
                        if not vidid or vidid == "None" or vidid == last_vidid: continue

                        dur_str = str(res.get("duration", "0:00"))
                        dur_sec = 0
                        if dur_str and ":" in dur_str:
                            parts = dur_str.split(":")
                            try:
                                if len(parts) == 2: dur_sec = int(parts[0]) * 60 + int(parts[1])
                                elif len(parts) == 3: dur_sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                            except ValueError: pass

                        if dur_sec < 30: continue
                        if max_duration and dur_sec > max_duration: continue

                        valid_choices.append({
                            "vidid": vidid,
                            "title": str(res.get("title", "Unknown Title")).title(),
                            "duration_min": dur_str,
                            "duration_sec": dur_sec
                        })
            except Exception: pass 

            if not valid_choices:
                # Removed cookies.txt
                ytdl_opts = {
                    "quiet": True, 
                    "extract_flat": True, 
                    "noplaylist": True,
                    "extractor_args": {"youtube": ["player_client=ios,tv_embedded"]} 
                } 
                ydl = yt_dlp.YoutubeDL(ytdl_opts)

                r = await _async_run(ydl.extract_info, f"ytsearch10:{search_query}", download=False)
                if r and "entries" in r:
                    for entry in r["entries"]:
                        vidid = entry.get("id")
                        if not vidid or vidid == last_vidid: continue

                        raw_dur = entry.get("duration", 0)
                        try: dur_sec = int(float(raw_dur)) if raw_dur else 0
                        except (ValueError, TypeError): dur_sec = 0

                        if not dur_sec or dur_sec < 30: continue
                        if max_duration and dur_sec > max_duration: continue

                        m, s = divmod(dur_sec, 60)
                        h, m = divmod(m, 60)
                        dur_str = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

                        valid_choices.append({
                            "vidid": vidid,
                            "title": str(entry.get("title", "Unknown Title")).title(),
                            "duration_min": dur_str,
                            "duration_sec": dur_sec
                        })

            if valid_choices: return random.choice(valid_choices)
            return None

        except Exception as e:
            LOGGER.error(f"YouTube Autoplay Function Error: {e}")
            return None

YouTube = YouTubeAPI()
                
