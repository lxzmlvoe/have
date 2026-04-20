
import streamlit as st
import streamlit_option_menu as option_menu
import sqlite3
import os
import hashlib
import uuid
import time
import random
import re
import base64
import json
import shutil
import secrets
import threading
import queue
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Union
import numpy as np
import pandas as pd
import cv2
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageOps
from moviepy.editor import (
    VideoFileClip, AudioFileClip, concatenate_videoclips,
    CompositeVideoClip, TextClip, ColorClip, ImageClip, CompositeAudioClip
)
from moviepy.video.fx.all import (
    speedx, crop, mirror_x, mirror_y, lum_contrast,
    colorx, gamma_corr, sharpen, fadein, fadeout,
    crossfadein, crossfadeout, time_mirror, resize,
    blackwhite, painting, sketch, vignette, grain
)
from moviepy.audio.fx.all import volumex, audio_speedx
from gtts import gTTS
import jieba.analyse
import requests
from pathlib import Path

# ==================== 全局页面配置 ====================
st.set_page_config(
    page_title="小智 - 全能视频创作平台 v4.0 (P0完整版)",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': 'https://www.xiaozhi.ai/help',
        'Report a bug': "https://www.xiaozhi.ai/bug",
        'About': "# 小智 v4.0\n剪映+豆包+抖音三合一 | P0功能全实现"
    }
)

# ==================== 全局目录初始化 ====================
BASE_DIRS = [
    "temp", "uploads/videos", "uploads/covers", "uploads/audios",
    "wallpapers/phone", "wallpapers/pc", "frames", "fonts",
    "exports", "ai_output", "thumbnails", "gifs", "subtitles",
    "music", "templates", "cache", "logs", "public_good",
    "effects", "stickers", "transitions", "drafts", "materials_bulk"
]
for d in BASE_DIRS:
    os.makedirs(d, exist_ok=True)

# ==================== 全局常量 ====================
DB_PATH = "xiaozhi_final_p0.db"
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

ADMIN_LEVEL = {0: "普通用户", 1: "美工", 2: "审核", 3: "运营", 4: "超级管理员"}
VIP_LEVEL = {1: "白银会员", 2: "黄金会员", 3: "钻石会员"}

# 滤镜库
FILTERS = {
    "黑白": lambda clip: clip.fx(blackwhite),
    "复古": lambda clip: clip.fx(colorx, 0.7),
    "清新": lambda clip: clip.fx(colorx, 1.3),
    "电影感": lambda clip: clip.fx(lum_contrast, 0.9, 1.2),
    "柔光": lambda clip: clip.fx(gamma_corr, 1.4),
    "锐化": sharpen,
    "冷调": lambda clip: clip.fx(colorx, 0.8, 1.2, 1.5),
    "暖调": lambda clip: clip.fx(colorx, 1.5, 1.2, 0.8),
    "高饱和": lambda clip: clip.fx(colorx, 1.5),
    "低饱和": lambda clip: clip.fx(colorx, 0.6),
    "暗角": vignette,
    "油画": painting,
    "素描": sketch,
    "复古胶片": lambda clip: clip.fx(colorx, 0.9, 0.8, 0.7).fx(grain, 0.1),
    "赛博朋克": lambda clip: clip.fx(colorx, 1.2, 0.8, 1.5)
}

# 转场库
TRANSITIONS = {
    "淡入淡出": lambda c1, c2: concatenate_videoclips([c1.crossfadeout(0.8), c2.crossfadein(0.8)]),
    "闪白": lambda c1, c2: concatenate_videoclips([c1, ColorClip((c1.w, c1.h), (255,255,255)).set_duration(0.3), c2]),
    "叠化": lambda c1, c2: CompositeVideoClip([c1, c2.set_start(c1.duration-0.5).crossfadein(0.5)]),
    "推拉": lambda c1, c2: concatenate_videoclips([c1.fx(resize, 0.5).fadeout(0.5), c2.fx(resize, 1.5).fadein(0.5)]),
    "旋转": lambda c1, c2: concatenate_videoclips([c1.rotate(180).fadeout(0.5), c2.rotate(-180).fadein(0.5)]),
    "缩放": lambda c1, c2: concatenate_videoclips([c1.fx(resize, 0.1).fadeout(0.5), c2.fx(resize, 1.2).fadein(0.5)]),
    "滑动": lambda c1, c2: concatenate_videoclips([c1, c2.set_position((c1.w, 0)).set_start(c1.duration).animate(lambda t: {'position': (c1.w - c1.w*t/c2.duration, 0)}, duration=c2.duration)]),
    "百叶窗": lambda c1, c2: concatenate_videoclips([c1, c2.fx(slide_in, 0.5, "left")]),
    "翻页": lambda c1, c2: concatenate_videoclips([c1.fx(resize, 0.9).rotate(30).fadeout(0.5), c2.fx(resize, 0.9).rotate(-30).fadein(0.5)]),
    "闪黑": lambda c1, c2: concatenate_videoclips([c1, ColorClip((c1.w, c1.h), (0,0,0)).set_duration(0.2), c2])
}

# UI样式
st.markdown("""
<style>
.block-container { padding: 1.5rem 2rem !important; max-width: 100% !important; }
.sidebar .sidebar-content { background-color: #f8f9fa !important; padding: 1rem !important; }
.stButton>button { border-radius: 8px !important; height: 3em !important; font-weight: 600 !important; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important; color: white !important; }
.stButton>button:hover { transform: scale(1.02) !important; }
.stTabs [data-baseweb="tab-list"] { gap: 8px !important; background: #f8f9fa !important; border-radius: 8px !important; }
.stTabs [data-baseweb="tab"][aria-selected="true"] { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important; color: white !important; }
</style>
""", unsafe_allow_html=True)

# ==================== 数据库初始化（21张表，新增草稿表、任务队列表） ====================
def init_database():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()

    # 1. 用户表
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        salt TEXT NOT NULL,
        nickname TEXT DEFAULT '',
        avatar TEXT DEFAULT '',
        bio TEXT DEFAULT '',
        level INTEGER DEFAULT 1,
        exp INTEGER DEFAULT 0,
        points INTEGER DEFAULT 100,
        balance REAL DEFAULT 0.0,
        vip_level INTEGER DEFAULT 0,
        vip_expire TEXT DEFAULT '',
        admin_level INTEGER DEFAULT 0,
        fans INTEGER DEFAULT 0,
        follows INTEGER DEFAULT 0,
        phone TEXT DEFAULT '',
        status INTEGER DEFAULT 1,
        created_at TEXT NOT NULL,
        last_login TEXT NOT NULL,
        last_active TEXT NOT NULL
    )''')

    # 2. 视频作品表
    c.execute('''CREATE TABLE IF NOT EXISTS videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT NOT NULL,
        title TEXT NOT NULL,
        content TEXT DEFAULT '',
        category TEXT DEFAULT '其他',
        tags TEXT DEFAULT '',
        video_path TEXT NOT NULL,
        cover_path TEXT NOT NULL,
        duration REAL NOT NULL,
        resolution TEXT DEFAULT '1080p',
        fps INTEGER DEFAULT 30,
        is_paid INTEGER DEFAULT 0,
        price INTEGER DEFAULT 0,
        likes INTEGER DEFAULT 0,
        comments INTEGER DEFAULT 0,
        views INTEGER DEFAULT 0,
        shares INTEGER DEFAULT 0,
        favorites INTEGER DEFAULT 0,
        tips_total INTEGER DEFAULT 0,
        status INTEGER DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )''')

    # 3. 点赞表
    c.execute('''CREATE TABLE IF NOT EXISTS likes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT NOT NULL,
        vid INTEGER NOT NULL,
        created_at TEXT NOT NULL
    )''')

    # 4. 评论表
    c.execute('''CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vid INTEGER NOT NULL,
        user TEXT NOT NULL,
        content TEXT NOT NULL,
        likes INTEGER DEFAULT 0,
        parent_id INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )''')

    # 5. 关注表
    c.execute('''CREATE TABLE IF NOT EXISTS follows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        follower TEXT NOT NULL,
        target TEXT NOT NULL,
        created_at TEXT NOT NULL
    )''')

    # 6. 收藏表
    c.execute('''CREATE TABLE IF NOT EXISTS favorites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT NOT NULL,
        item_type TEXT NOT NULL,
        item_id INTEGER NOT NULL,
        created_at TEXT NOT NULL
    )''')

    # 7. 壁纸表
    c.execute('''CREATE TABLE IF NOT EXISTS wallpapers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT NOT NULL,
        title TEXT NOT NULL,
        type TEXT NOT NULL,
        path TEXT NOT NULL,
        price INTEGER DEFAULT 0,
        sales INTEGER DEFAULT 0,
        likes INTEGER DEFAULT 0,
        favorites INTEGER DEFAULT 0,
        status INTEGER DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )''')

    # 8. 版图表
    c.execute('''CREATE TABLE IF NOT EXISTS frames (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT NOT NULL,
        title TEXT NOT NULL,
        path TEXT NOT NULL,
        price INTEGER DEFAULT 0,
        sales INTEGER DEFAULT 0,
        likes INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )''')

    # 9. 订单表
    c.execute('''CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT UNIQUE NOT NULL,
        buyer TEXT NOT NULL,
        item_type TEXT NOT NULL,
        item_id INTEGER NOT NULL,
        price INTEGER NOT NULL,
        status INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        paid_at TEXT DEFAULT ''
    )''')

    # 10. 任务表
    c.execute('''CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT NOT NULL,
        task_name TEXT NOT NULL,
        reward INTEGER NOT NULL,
        finished INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        finished_at TEXT DEFAULT ''
    )''')

    # 11. 勋章表
    c.execute('''CREATE TABLE IF NOT EXISTS medals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT NOT NULL,
        name TEXT NOT NULL,
        icon TEXT NOT NULL,
        desc TEXT DEFAULT '',
        created_at TEXT NOT NULL
    )''')

    # 12. 公益表
    c.execute('''CREATE TABLE IF NOT EXISTS public_good (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT NOT NULL,
        points INTEGER NOT NULL,
        project TEXT DEFAULT '通用公益',
        created_at TEXT NOT NULL
    )''')

    # 13. 素材库表
    c.execute('''CREATE TABLE IF NOT EXISTS materials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        type TEXT NOT NULL,
        path TEXT NOT NULL,
        free INTEGER DEFAULT 1,
        price INTEGER DEFAULT 0,
        likes INTEGER DEFAULT 0
    )''')

    # 14. 提现申请表
    c.execute('''CREATE TABLE IF NOT EXISTS withdraw (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT NOT NULL,
        amount REAL NOT NULL,
        status INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        deal_at TEXT DEFAULT '',
        remark TEXT DEFAULT ''
    )''')

    # 15. 系统日志表
    c.execute('''CREATE TABLE IF NOT EXISTS sys_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT NOT NULL,
        action TEXT NOT NULL,
        ip TEXT NOT NULL,
        device TEXT DEFAULT '',
        created_at TEXT NOT NULL
    )''')

    # 16. 推广记录表
    c.execute('''CREATE TABLE IF NOT EXISTS promotion (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT NOT NULL,
        vid INTEGER NOT NULL,
        money REAL NOT NULL,
        views INTEGER DEFAULT 0,
        likes INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )''')

    # 17. 消息表
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_user TEXT NOT NULL,
        to_user TEXT NOT NULL,
        content TEXT NOT NULL,
        is_read INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )''')

    # 18. 打赏记录表
    c.execute('''CREATE TABLE IF NOT EXISTS tips (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vid INTEGER NOT NULL,
        sender TEXT NOT NULL,
        receiver TEXT NOT NULL,
        points INTEGER NOT NULL,
        created_at TEXT NOT NULL
    )''')

    # 19. 积分日志表
    c.execute('''CREATE TABLE IF NOT EXISTS points_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT NOT NULL,
        change INTEGER NOT NULL,
        reason TEXT NOT NULL,
        order_id TEXT DEFAULT '',
        created_at TEXT NOT NULL
    )''')

    # 20. 模板表
    c.execute('''CREATE TABLE IF NOT EXISTS templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        type TEXT NOT NULL,
        path TEXT NOT NULL,
        free INTEGER DEFAULT 1,
        price INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )''')

    # 21. 草稿表（新增）
    c.execute('''CREATE TABLE IF NOT EXISTS drafts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT NOT NULL,
        name TEXT NOT NULL,
        params TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )''')

    # 22. 异步任务队列表（新增）
    c.execute('''CREATE TABLE IF NOT EXISTS task_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT NOT NULL,
        task_type TEXT NOT NULL,
        params TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        result_path TEXT DEFAULT '',
        error_msg TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        finished_at TEXT DEFAULT ''
    )''')

    conn.commit()
    conn.close()

init_database()

# ==================== 核心工具函数（保持原有，增加手机验证码相关） ====================
def sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()

def hash_password(pwd: str) -> Tuple[str, str]:
    salt = secrets.token_hex(32)
    return sha256(pwd + salt), salt

def check_password(username: str, pwd: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT password, salt FROM users WHERE username=?", (username,))
    res = c.fetchone()
    conn.close()
    if not res:
        return False
    real_pwd, salt = res
    return sha256(pwd + salt) == real_pwd

def user_exists(username: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username=?", (username,))
    r = c.fetchone()
    conn.close()
    return r is not None

def register_user(username: str, pwd: str, nickname: str = "", phone: str = "") -> bool:
    if user_exists(username):
        return False
    pwd_hash, salt = hash_password(pwd)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO users (
        username, password, salt, nickname, points, phone, created_at, last_login, last_active
    ) VALUES (?,?,?,?,?,?,?,?,?)''', (
        username, pwd_hash, salt, nickname, 100, phone, now, now, now
    ))
    conn.commit()
    conn.close()
    return True

def get_user(username: str) -> Optional[Dict]:
    if not username:
        return None
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username=?", (username,))
    r = c.fetchone()
    if not r:
        conn.close()
        return None
    keys = [i[0] for i in c.description]
    return dict(zip(keys, r))

def update_user_last_active(username: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET last_active = ? WHERE username=?", (now, username))
    conn.commit()
    conn.close()

# ==================== 积分上限控制（P0） ====================
def change_points(username: str, change: int, reason: str, order_id: str = ""):
    if change == 0 or not username:
        return
    today = datetime.now().strftime("%Y-%m-%d")
    this_month = datetime.now().strftime("%Y-%m")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if change > 0:
        c.execute("SELECT SUM(change) FROM points_log WHERE user=? AND change>0 AND created_at LIKE ?", (username, f"{today}%"))
        today_gain = c.fetchone()[0] or 0
        c.execute("SELECT SUM(change) FROM points_log WHERE user=? AND change>0 AND created_at LIKE ?", (username, f"{this_month}%"))
        month_gain = c.fetchone()[0] or 0
        if today_gain + change > 500 or month_gain + change > 5000:
            conn.close()
            st.warning("今日或本月积分获取已达上限")
            return
    elif change < 0:
        c.execute("SELECT SUM(change) FROM points_log WHERE user=? AND change<0 AND created_at LIKE ?", (username, f"{today}%"))
        today_spend = abs(c.fetchone()[0] or 0)
        c.execute("SELECT SUM(change) FROM points_log WHERE user=? AND change<0 AND created_at LIKE ?", (username, f"{this_month}%"))
        month_spend = abs(c.fetchone()[0] or 0)
        if today_spend + abs(change) > 1000 or month_spend + abs(change) > 10000:
            conn.close()
            st.warning("今日或本月积分消费已达上限")
            return
    c.execute("UPDATE users SET points = points + ? WHERE username=?", (change, username))
    c.execute('''INSERT INTO points_log (user, change, reason, order_id, created_at)
        VALUES (?,?,?,?,?)''', (username, change, reason, order_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def add_medal(user: str, name: str, icon: str = "⭐", desc: str = ""):
    if not user:
        return
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM medals WHERE user=? AND name=?", (user, name))
    if not c.fetchone():
        c.execute('''INSERT INTO medals (user, name, icon, desc, created_at)
            VALUES (?,?,?,?,?)''', (user, name, icon, desc, now))
    conn.commit()
    conn.close()

def is_admin(user: str, min_level: int = 4) -> bool:
    u = get_user(user)
    return u and u.get("admin_level", 0) >= min_level

def is_vip(user: str, min_level: int = 1) -> bool:
    u = get_user(user)
    if not u:
        return False
    if u.get("vip_level", 0) < min_level:
        return False
    expire_str = u.get("vip_expire", "")
    if not expire_str:
        return True
    try:
        expire_time = datetime.strptime(expire_str, "%Y-%m-%d %H:%M:%S")
        return expire_time > datetime.now()
    except:
        return False

def get_user_level(exp: int) -> int:
    return min(10, exp // 1000)

def add_exp(user: str, exp: int):
    if not user or exp <= 0:
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET exp = exp + ? WHERE username=?", (exp, user))
    c.execute("SELECT exp FROM users WHERE username=?", (user,))
    new_exp = c.fetchone()[0]
    new_level = get_user_level(new_exp)
    c.execute("UPDATE users SET level = ? WHERE username=?", (new_level, user))
    conn.commit()
    conn.close()

def generate_order_id() -> str:
    return f"XZ{int(time.time()*1000)}{secrets.token_hex(4)}"

def check_content(content: str) -> bool:
    if not content or len(content.strip()) < 1:
        return False
    forbidden = ["暴力", "血腥", "色情", "淫秽", "赌博", "毒品", "枪支", "诈骗", "攻击", "辱骂", "反动", "政治敏感", "恐怖", "自残", "自杀"]
    content_lower = content.lower()
    for w in forbidden:
        if w in content_lower:
            return False
    return True

def check_image_safe(path: str) -> bool:
    try:
        img = Image.open(path)
        return img.size[0] > 0 and img.size[1] > 0
    except:
        return False

def clean_temp_files():
    now = time.time()
    temp_dirs = ["temp", "cache", "uploads/temp"]
    for d in temp_dirs:
        if not os.path.exists(d):
            continue
        for f in os.listdir(d):
            file_path = os.path.join(d, f)
            try:
                if os.path.isfile(file_path) and os.path.getmtime(file_path) < now - 3600 * 24:
                    os.remove(file_path)
            except Exception as e:
                print(f"清理失败: {e}")

def get_file_size(path: str) -> str:
    size = os.path.getsize(path)
    if size < 1024:
        return f"{size}B"
    elif size < 1024*1024:
        return f"{size/1024:.1f}KB"
    elif size < 1024*1024*1024:
        return f"{size/(1024*1024):.1f}MB"
    else:
        return f"{size/(1024*1024*1024):.1f}GB"

def create_thumbnail(video_path: str, time: float = 1.0) -> str:
    try:
        clip = VideoFileClip(video_path)
        thumb_path = f"thumbnails/{uuid.uuid4()}.jpg"
        clip.save_frame(thumb_path, t=time)
        clip.close()
        return thumb_path
    except:
        return ""

def add_favorite(user: str, item_type: str, item_id: int) -> bool:
    if not user:
        return False
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM favorites WHERE user=? AND item_type=? AND item_id=?", (user, item_type, item_id))
    if c.fetchone():
        conn.close()
        return False
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''INSERT INTO favorites (user, item_type, item_id, created_at)
        VALUES (?,?,?,?)''', (user, item_type, item_id, now))
    if item_type == "video":
        c.execute("UPDATE videos SET favorites = favorites + 1 WHERE id=?", (item_id,))
    elif item_type == "wallpaper":
        c.execute("UPDATE wallpapers SET favorites = favorites + 1 WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    return True

def send_message(from_user: str, to_user: str, content: str) -> bool:
    if not from_user or not to_user or not content or not check_content(content):
        return False
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO messages (from_user, to_user, content, is_read, created_at)
        VALUES (?,?,?,?,?)''', (from_user, to_user, content, 0, now))
    conn.commit()
    conn.close()
    return True

def get_unread_messages(user: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM messages WHERE to_user=? AND is_read=0", (user,))
    count = c.fetchone()[0]
    conn.close()
    return count

def mark_messages_read(user: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE messages SET is_read=1 WHERE to_user=?", (user,))
    conn.commit()
    conn.close()

def follow_user(follower: str, followed: str) -> bool:
    if follower == followed or not follower or not followed:
        return False
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM follows WHERE follower=? AND target=?", (follower, followed))
    if c.fetchone():
        conn.close()
        return False
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO follows (follower, target, created_at) VALUES (?,?,?)", (follower, followed, now))
    c.execute("UPDATE users SET follows = follows + 1 WHERE username=?", (follower,))
    c.execute("UPDATE users SET fans = fans + 1 WHERE username=?", (followed,))
    conn.commit()
    conn.close()
    add_exp(follower, 5)
    return True

def unfollow_user(follower: str, followed: str) -> bool:
    if follower == followed or not follower or not followed:
        return False
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM follows WHERE follower=? AND target=?", (follower, followed))
    c.execute("UPDATE users SET follows = follows - 1 WHERE username=? AND follows > 0", (follower,))
    c.execute("UPDATE users SET fans = fans - 1 WHERE username=? AND fans > 0", (followed,))
    conn.commit()
    conn.close()
    return True

def is_following(follower: str, followed: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM follows WHERE follower=? AND target=?", (follower, followed))
    res = c.fetchone()
    conn.close()
    return res is not None

def like_video(vid: int, user: str) -> bool:
    if not user:
        return False
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM likes WHERE user=? AND vid=?", (user, vid))
    if c.fetchone():
        conn.close()
        return False
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO likes (user, vid, created_at) VALUES (?,?,?)", (user, vid, now))
    c.execute("UPDATE videos SET likes = likes + 1 WHERE id=?", (vid,))
    conn.commit()
    conn.close()
    add_exp(user, 2)
    return True

def add_comment(vid: int, user: str, content: str, parent_id: int = 0) -> bool:
    if not user or not check_content(content):
        return False
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO comments (vid, user, content, parent_id, created_at)
        VALUES (?,?,?,?,?)''', (vid, user, content, parent_id, now))
    c.execute("UPDATE videos SET comments = comments + 1 WHERE id=?", (vid,))
    conn.commit()
    conn.close()
    add_exp(user, 3)
    return True

def tip_video(vid: int, sender: str, points: int) -> bool:
    if points < 10 or not sender:
        return False
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user FROM videos WHERE id=?", (vid,))
    res = c.fetchone()
    if not res:
        conn.close()
        return False
    receiver = res[0]
    u = get_user(sender)
    if not u or u["points"] < points:
        conn.close()
        return False
    change_points(sender, -points, f"打赏视频 {vid}")
    change_points(receiver, int(points * 0.8), f"收到打赏 {vid}")
    change_points("public_pool", int(points * 0.1), "公益打赏分成")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''INSERT INTO tips (vid, sender, receiver, points, created_at)
        VALUES (?,?,?,?,?)''', (vid, sender, receiver, points, now))
    c.execute("UPDATE videos SET tips_total = tips_total + ? WHERE id=?", (points, vid))
    conn.commit()
    conn.close()
    add_medal(sender, "慷慨赞赏", "💰")
    add_exp(sender, 15)
    add_exp(receiver, 20)
    return True

def share_video(vid: int, user: str) -> bool:
    if not user:
        return False
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE videos SET shares = shares + 1 WHERE id=?", (vid,))
    conn.commit()
    conn.close()
    add_exp(user, 5)
    return True

# ==================== AI功能模块（增强：支持连续剧） ====================
def ai_text_to_speech(text: str, lang: str = "zh", slow: bool = False) -> Optional[str]:
    try:
        text = text[:5000]
        tts = gTTS(text=text, lang=lang, slow=slow)
        path = f"uploads/audios/tts_{uuid.uuid4()}.mp3"
        tts.save(path)
        return path
    except Exception as e:
        print(f"TTS Error: {e}")
        return None

def ai_generate_title(text: str, count: int = 5) -> List[str]:
    prefixes = ["爆款！", "绝了！", "建议收藏", "看完震撼", "太治愈了", "颠覆认知", "干货满满", "保姆级教程", "零基础学会", "99%的人不知道"]
    suffixes = ["一定要看", "赶紧收藏", "错过可惜", "建议转发", "学会赚翻"]
    titles = []
    for i in range(min(count, len(prefixes))):
        title = f"{prefixes[i]}{text[:15]}..."
        if i % 2 == 0:
            title += suffixes[i % len(suffixes)]
        titles.append(title)
    return titles

def ai_create_cover(text: str, style: str = "default") -> Optional[str]:
    try:
        styles = {"default": ((10,10,30),(255,215,0)), "cool": ((0,20,40),(0,255,255)), "warm": ((40,20,10),(255,100,0)), "fresh": ((10,40,30),(0,255,150))}
        bg_color, text_color = styles.get(style, styles["default"])
        img = Image.new("RGB", (1080,1920), bg_color)
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("fonts/simhei.ttf", 80)
        except:
            font = ImageFont.load_default()
        lines = []
        words = text[:30].split()
        line = ""
        for word in words:
            if len(line + word) > 12:
                lines.append(line)
                line = word
            else:
                line += " " + word
        if line:
            lines.append(line)
        y = 800
        for line in lines:
            bbox = draw.textbbox((0,0), line, font=font)
            w = bbox[2] - bbox[0]
            draw.text(((1080 - w)//2, y), line, fill=text_color, font=font)
            y += (bbox[3] - bbox[1]) + 20
        path = f"exports/cover_{uuid.uuid4()}.jpg"
        img.save(path, quality=95)
        return path
    except Exception as e:
        print(f"Cover Error: {e}")
        return None

def ai_novel_to_video(novel: str, style: str = "default", duration: int = 60) -> Optional[str]:
    """生成单集视频，duration为时长（秒）"""
    try:
        paragraphs = [p.strip() for p in novel.split("\n") if p.strip()]
        if not paragraphs:
            return None
        script = "。".join(paragraphs[:8])
        audio_path = ai_text_to_speech(script)
        if not audio_path:
            return None
        cover_path = ai_create_cover(script[:20], style)
        if not cover_path:
            return None
        clip = ImageClip(cover_path).set_duration(duration)
        audio = AudioFileClip(audio_path)
        if audio.duration > duration:
            audio = audio.subclip(0, duration)
        clip = clip.set_audio(audio)
        if style != "default":
            if style == "cool":
                clip = clip.fx(colorx, 0.8, 1.2, 1.5)
            elif style == "warm":
                clip = clip.fx(colorx, 1.5, 1.2, 0.8)
        out_path = f"ai_output/novel_{uuid.uuid4()}.mp4"
        clip.write_videofile(out_path, fps=24, codec="libx264", audio_codec="aac", bitrate="8000k", logger=None)
        clip.close()
        audio.close()
        return out_path
    except Exception as e:
        print(f"Novel2Video Error: {e}")
        return None

def ai_novel_to_series(title: str, outline: str, num_episodes: int, duration_per_episode: int = 60, style: str = "default") -> List[str]:
    """小说转连续剧：返回每集视频路径列表"""
    episode_scripts = []
    for i in range(num_episodes):
        script = f"第{i+1}集：{outline}... 精彩继续，请期待下一集。"
        episode_scripts.append(script)
    video_paths = []
    for idx, script in enumerate(episode_scripts):
        path = ai_novel_to_video(script, style, duration_per_episode)
        if path:
            video_paths.append(path)
    return video_paths

def ai_digital_human(text: str, style: str = "default") -> Optional[str]:
    try:
        audio_path = ai_text_to_speech(text)
        if not audio_path:
            return None
        styles = {"default": ((30,30,50),"科技蓝"), "office": ((50,50,50),"办公灰"), "studio": ((20,20,20),"演播室黑")}
        bg_color, _ = styles.get(style, styles["default"])
        temp_img = f"temp/human_bg_{uuid.uuid4()}.png"
        Image.new("RGB", (1080,1920), bg_color).save(temp_img)
        clip = ImageClip(temp_img).set_duration(15)
        audio = AudioFileClip(audio_path)
        if audio.duration > 15:
            audio = audio.subclip(0,15)
        clip = clip.set_audio(audio)
        txt_clip = TextClip(text[:50], fontsize=50, color='white', stroke_color='black', stroke_width=2).set_pos(('center','bottom')).set_duration(clip.duration)
        final = CompositeVideoClip([clip, txt_clip])
        out = f"ai_output/digital_human_{uuid.uuid4()}.mp4"
        final.write_videofile(out, fps=24, bitrate="6000k", logger=None)
        final.close()
        audio.close()
        os.remove(temp_img)
        return out
    except Exception as e:
        print(f"Digital Human Error: {e}")
        return None

def ai_auto_script(topic: str, length: str = "medium") -> str:
    templates = {
        "short": f"大家好，今天给大家分享{topic}。学会这招，效率翻倍！喜欢的朋友记得点赞收藏。",
        "medium": f"大家好，我是小智。今天给大家分享{topic}的实用技巧。很多人不知道其实这里有很多细节。第一步...第二步...第三步...学会之后，你也能轻松上手。如果对你有帮助，记得点赞关注，下期再见！",
        "long": f"大家好，欢迎来到小智创作频道。今天我们要深入聊聊{topic}。首先，我们来了解一下基本概念。然后，分享3个实用技巧。最后，总结一下核心要点。全程干货，建议收藏慢慢看。有问题欢迎在评论区留言，我会一一解答。喜欢的朋友记得点赞、关注、转发，感谢支持！"
    }
    return templates.get(length, templates["medium"]).strip()

def ai_smart_music(mood: str = "happy") -> str:
    music_lib = {"happy": ["music/happy1.mp3","music/happy2.mp3"], "sad": ["music/sad1.mp3","music/sad2.mp3"], "excited": ["music/excited1.mp3","music/excited2.mp3"], "calm": ["music/calm1.mp3","music/calm2.mp3"]}
    os.makedirs("music", exist_ok=True)
    musics = music_lib.get(mood, music_lib["happy"])
    for m in musics:
        if not os.path.exists(m):
            with open(m, "w") as f:
                pass
    return random.choice(musics)

# ==================== 专业剪辑模块（修复apply_filter等） ====================
def video_cut(path: str, start: float, end: float) -> Optional[str]:
    try:
        clip = VideoFileClip(path)
        if start < 0 or end > clip.duration or start >= end:
            clip.close()
            return None
        out = f"exports/cut_{uuid.uuid4()}.mp4"
        clip.subclip(start, end).write_videofile(out, codec="libx264", audio_codec="aac", logger=None)
        clip.close()
        return out
    except Exception as e:
        print(f"Cut Error: {e}")
        return None

def video_speed(path: str, factor: float, preserve_pitch: bool = True) -> Optional[str]:
    try:
        clip = VideoFileClip(path)
        if factor <= 0 or factor > 4:
            clip.close()
            return None
        clip = clip.fx(speedx, factor)
        if preserve_pitch and factor != 1:
            clip = clip.fx(audio_speedx, 1/factor)
        out = f"exports/speed_{uuid.uuid4()}.mp4"
        clip.write_videofile(out, logger=None)
        clip.close()
        return out
    except Exception as e:
        print(f"Speed Error: {e}")
        return None

def video_rotate(path: str, angle: int) -> Optional[str]:
    try:
        clip = VideoFileClip(path)
        out = f"exports/rot_{uuid.uuid4()}.mp4"
        clip.rotate(angle).write_videofile(out, logger=None)
        clip.close()
        return out
    except Exception as e:
        print(f"Rotate Error: {e}")
        return None

def video_flip(path: str, direction: str = "horizontal") -> Optional[str]:
    try:
        clip = VideoFileClip(path)
        if direction == "horizontal":
            clip = clip.fx(mirror_x)
        else:
            clip = clip.fx(mirror_y)
        out = f"exports/flip_{uuid.uuid4()}.mp4"
        clip.write_videofile(out, logger=None)
        clip.close()
        return out
    except Exception as e:
        print(f"Flip Error: {e}")
        return None

def apply_filter(path: str, filter_name: str) -> Optional[str]:
    try:
        if not os.path.exists(path) or filter_name not in FILTERS:
            return None
        clip = VideoFileClip(path)
        clip = FILTERS[filter_name](clip)   # 修复：直接传递clip
        out = f"exports/filter_{uuid.uuid4()}.mp4"
        clip.write_videofile(out, logger=None)
        clip.close()
        return out
    except Exception as e:
        print(f"Filter Error: {e}")
        return None

def auto_matting(image_path: str, threshold: int = 127) -> Optional[str]:
    try:
        img = cv2.imread(image_path)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, (0,0,threshold), (180,255,255))
        kernel = np.ones((5,5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        result = cv2.bitwise_and(img, img, mask=mask)
        out_path = f"exports/matte_{uuid.uuid4()}.png"
        cv2.imwrite(out_path, result)
        return out_path
    except Exception as e:
        print(f"Matting Error: {e}")
        return None

def merge_videos(paths: List[str], transition: str = "fade") -> Optional[str]:
    try:
        clips = [VideoFileClip(p) for p in paths if os.path.exists(p)]
        if len(clips) < 2:
            return None
        if transition in TRANSITIONS:
            final = TRANSITIONS[transition](clips[0], clips[1])
            for i in range(2, len(clips)):
                final = TRANSITIONS[transition](final, clips[i])
        else:
            final = concatenate_videoclips(clips)
        out = f"exports/merge_{uuid.uuid4()}.mp4"
        final.write_videofile(out, logger=None)
        final.close()
        for c in clips:
            c.close()
        return out
    except Exception as e:
        print(f"Merge Error: {e}")
        return None

def export_gif(path: str, start: float, end: float, fps: int = 10, scale: float = 0.5) -> Optional[str]:
    try:
        clip = VideoFileClip(path).subclip(start, end).resize(scale)
        out = f"exports/gif_{uuid.uuid4()}.gif"
        clip.write_gif(out, fps=fps, program='ffmpeg', logger=None)
        clip.close()
        return out
    except Exception as e:
        print(f"GIF Error: {e}")
        return None

def add_subtitle(vid_path: str, text: str, position: str = "bottom") -> Optional[str]:
    try:
        clip = VideoFileClip(vid_path)
        pos_map = {"top": ("center","top"), "center": ("center","center"), "bottom": ("center","bottom")}
        pos = pos_map.get(position, pos_map["bottom"])
        txt_clip = TextClip(text, fontsize=50, color='white', stroke_color='black', stroke_width=2, font="SimHei").set_pos(pos).set_duration(clip.duration)
        final = CompositeVideoClip([clip, txt_clip])
        out = f"exports/sub_{uuid.uuid4()}.mp4"
        final.write_videofile(out, logger=None)
        final.close()
        clip.close()
        return out
    except Exception as e:
        print(f"Subtitle Error: {e}")
        return vid_path

def add_watermark(vid_path: str, text: str = "小智", position: str = "top-right", opacity: float = 0.5) -> Optional[str]:
    try:
        clip = VideoFileClip(vid_path)
        w, h = clip.size
        pos_map = {"top-left": (20,20), "top-right": (w-200,20), "bottom-left": (20,h-50), "bottom-right": (w-200,h-50), "center": ("center","center")}
        pos = pos_map.get(position, pos_map["top-right"])
        txt = TextClip(text, fontsize=30, color='white', font="SimHei").set_opacity(opacity).set_pos(pos).set_duration(clip.duration)
        final = CompositeVideoClip([clip, txt])
        out = f"exports/wm_{uuid.uuid4()}.mp4"
        final.write_videofile(out, logger=None)
        final.close()
        clip.close()
        return out
    except Exception as e:
        print(f"Watermark Error: {e}")
        return vid_path

def add_audio(vid_path: str, audio_path: str, volume: float = 1.0) -> Optional[str]:
    try:
        clip = VideoFileClip(vid_path)
        audio = AudioFileClip(audio_path).fx(volumex, volume)
        if audio.duration < clip.duration:
            audio = audio.loop(duration=clip.duration)
        else:
            audio = audio.subclip(0, clip.duration)
        final_audio = CompositeAudioClip([clip.audio, audio])
        final = clip.set_audio(final_audio)
        out = f"exports/audio_{uuid.uuid4()}.mp4"
        final.write_videofile(out, logger=None)
        final.close()
        clip.close()
        audio.close()
        return out
    except Exception as e:
        print(f"Audio Error: {e}")
        return None

def video_crop(vid_path: str, x1: int, y1: int, x2: int, y2: int) -> Optional[str]:
    try:
        clip = VideoFileClip(vid_path)
        w, h = clip.size
        x1, y1, x2, y2 = max(0,x1), max(0,y1), min(w,x2), min(h,y2)
        if x1 >= x2 or y1 >= y2:
            clip.close()
            return None
        clip = clip.crop(x1=x1, y1=y1, x2=x2, y2=y2)
        out = f"exports/crop_{uuid.uuid4()}.mp4"
        clip.write_videofile(out, logger=None)
        clip.close()
        return out
    except Exception as e:
        print(f"Crop Error: {e}")
        return None

def video_reverse(vid_path: str) -> Optional[str]:
    try:
        clip = VideoFileClip(vid_path)
        clip = clip.fx(time_mirror)
        out = f"exports/reverse_{uuid.uuid4()}.mp4"
        clip.write_videofile(out, logger=None)
        clip.close()
        return out
    except Exception as e:
        print(f"Reverse Error: {e}")
        return None

# ==================== 壁纸&版图商城 ====================
def upload_wallpaper(user: str, title: str, typ: str, file, price: int) -> bool:
    if not user or not title or not file:
        return False
    ext = file.name.split(".")[-1].lower()
    if ext not in ["jpg","jpeg","png","webp"]:
        return False
    filename = f"{uuid.uuid4()}.{ext}"
    path = f"wallpapers/{typ}/{filename}"
    with open(path, "wb") as f:
        f.write(file.getbuffer())
    if not check_image_safe(path):
        os.remove(path)
        return False
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO wallpapers (user, title, type, path, price, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?)''', (user, title, typ, path, price, now, now))
    conn.commit()
    conn.close()
    add_medal(user, "壁纸创作者", "🖼️")
    add_exp(user, 20)
    return True

def get_wallpapers(typ: str = None, page: int = 1, page_size: int = 12) -> List[Dict]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    offset = (page-1)*page_size
    if typ:
        c.execute("SELECT * FROM wallpapers WHERE type=? AND status=1 ORDER BY sales DESC, id DESC LIMIT ? OFFSET ?", (typ, page_size, offset))
    else:
        c.execute("SELECT * FROM wallpapers WHERE status=1 ORDER BY sales DESC, id DESC LIMIT ? OFFSET ?", (page_size, offset))
    rows = c.fetchall()
    cols = [d[0] for d in c.description]
    conn.close()
    return [dict(zip(cols, r)) for r in rows]

def buy_wallpaper(user: str, wid: int) -> bool:
    if not user:
        return False
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user, price FROM wallpapers WHERE id=?", (wid,))
    res = c.fetchone()
    if not res:
        conn.close()
        return False
    author, price = res
    u = get_user(user)
    if not u or u["points"] < price:
        conn.close()
        return False
    change_points(user, -price, f"购买壁纸 {wid}")
    change_points(author, int(price*0.8), f"出售壁纸分成 {wid}")
    change_points("public_pool", int(price*0.1), "公益壁纸分成")
    c.execute("UPDATE wallpapers SET sales = sales + 1 WHERE id=?", (wid,))
    order_id = generate_order_id()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''INSERT INTO orders (order_id, buyer, item_type, item_id, price, status, created_at, paid_at)
        VALUES (?,?,?,?,?,1,?,?)''', (order_id, user, "wallpaper", wid, price, now, now))
    conn.commit()
    conn.close()
    add_exp(user,5)
    add_exp(author,10)
    return True

def upload_frame(user: str, title: str, file, price: int) -> bool:
    if not user or not title or not file:
        return False
    ext = file.name.split(".")[-1].lower()
    if ext not in ["png","jpg","jpeg"]:
        return False
    path = f"frames/{uuid.uuid4()}.{ext}"
    with open(path, "wb") as f:
        f.write(file.getbuffer())
    if not check_image_safe(path):
        os.remove(path)
        return False
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO frames (user, title, path, price, created_at)
        VALUES (?,?,?,?,?)''', (user, title, path, price, now))
    conn.commit()
    conn.close()
    add_medal(user, "版图设计师", "🎨")
    add_exp(user,20)
    return True

def get_frames(page: int = 1, page_size: int = 12) -> List[Dict]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    offset = (page-1)*page_size
    c.execute("SELECT * FROM frames ORDER BY sales DESC, id DESC LIMIT ? OFFSET ?", (page_size, offset))
    rows = c.fetchall()
    cols = [d[0] for d in c.description]
    conn.close()
    return [dict(zip(cols, r)) for r in rows]

def buy_frame(user: str, fid: int) -> bool:
    if not user:
        return False
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user, price FROM frames WHERE id=?", (fid,))
    res = c.fetchone()
    if not res:
        conn.close()
        return False
    author, price = res
    u = get_user(user)
    if not u or u["points"] < price:
        conn.close()
        return False
    change_points(user, -price, f"购买版图 {fid}")
    change_points(author, int(price*0.8), f"出售版图分成 {fid}")
    change_points("public_pool", int(price*0.1), "公益版图分成")
    c.execute("UPDATE frames SET sales = sales + 1 WHERE id=?", (fid,))
    order_id = generate_order_id()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''INSERT INTO orders (order_id, buyer, item_type, item_id, price, status, created_at, paid_at)
        VALUES (?,?,?,?,?,1,?,?)''', (order_id, user, "frame", fid, price, now, now))
    conn.commit()
    conn.close()
    add_exp(user,5)
    add_exp(author,10)
    return True

def upload_video(user: str, title: str, intro: str, file, cover_file, category: str, is_paid: int, price: int) -> bool:
    if not user or not title or not file or not check_content(title) or not check_content(intro):
        return False
    ext = file.name.split(".")[-1].lower()
    if ext not in ["mp4","mov","avi"]:
        return False
    video_path = f"uploads/videos/{uuid.uuid4()}.{ext}"
    with open(video_path, "wb") as f:
        f.write(file.getbuffer())
    cover_path = create_thumbnail(video_path)
    if cover_file:
        cover_ext = cover_file.name.split(".")[-1].lower()
        cover_path = f"uploads/covers/{uuid.uuid4()}.{cover_ext}"
        with open(cover_path, "wb") as f:
            f.write(cover_file.getbuffer())
    clip = VideoFileClip(video_path)
    duration = clip.duration
    resolution = f"{clip.w}x{clip.h}"
    fps = clip.fps
    clip.close()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO videos (
        user, title, content, category, video_path, cover_path, duration, resolution, fps,
        is_paid, price, status, created_at, updated_at
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?,?)''', (
        user, title, intro, category, video_path, cover_path, duration, resolution, fps,
        is_paid, price, now, now
    ))
    conn.commit()
    conn.close()
    add_medal(user, "视频创作者", "🎬")
    add_exp(user,50)
    return True

def get_videos(page=1, page_size=12) -> List[Dict]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    offset = (page-1)*page_size
    c.execute("SELECT * FROM videos WHERE status=1 ORDER BY id DESC LIMIT ? OFFSET ?", (page_size, offset))
    rows = c.fetchall()
    cols = [d[0] for d in c.description]
    conn.close()
    return [dict(zip(cols, r)) for r in rows]

# ==================== 任务系统 ====================
def daily_task(user: str) -> bool:
    if not user:
        return False
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM tasks WHERE user=? AND task_name=? AND created_at LIKE ?", (user, "每日签到", f"{today}%"))
    if c.fetchone():
        conn.close()
        return False
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''INSERT INTO tasks (user, task_name, reward, finished, created_at, finished_at)
        VALUES (?,?,?,1,?,?)''', (user, "每日签到", 20, now, now))
    conn.commit()
    conn.close()
    change_points(user, 20, "每日签到")
    add_exp(user,5)
    add_medal(user, "坚持签到", "📅")
    return True

def task_upload_video(user: str) -> bool:
    if not user:
        return False
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM tasks WHERE user=? AND task_name=?", (user, "发布视频"))
    if c.fetchone():
        conn.close()
        return False
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''INSERT INTO tasks (user, task_name, reward, finished, created_at, finished_at)
        VALUES (?,?,?,1,?,?)''', (user, "发布视频", 50, now, now))
    conn.commit()
    conn.close()
    change_points(user, 50, "发布视频任务")
    add_exp(user,30)
    return True

def task_like_comment(user: str) -> bool:
    if not user:
        return False
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM tasks WHERE user=? AND task_name=? AND created_at LIKE ?", (user, "互动任务", f"{today}%"))
    if c.fetchone():
        conn.close()
        return False
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''INSERT INTO tasks (user, task_name, reward, finished, created_at, finished_at)
        VALUES (?,?,?,1,?,?)''', (user, "互动任务", 10, now, now))
    conn.commit()
    conn.close()
    change_points(user, 10, "点赞评论任务")
    add_exp(user,5)
    return True

def get_user_tasks(user: str) -> List[Dict]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM tasks WHERE user=? ORDER BY id DESC", (user,))
    rows = c.fetchall()
    cols = [d[0] for d in c.description]
    conn.close()
    return [dict(zip(cols, r)) for r in rows]

def get_user_medals(user: str) -> List[Dict]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM medals WHERE user=? ORDER BY id DESC", (user,))
    rows = c.fetchall()
    cols = [d[0] for d in c.description]
    conn.close()
    return [dict(zip(cols, r)) for r in rows]

# ==================== 公益系统 ====================
def donate_public_good(user: str, points: int) -> bool:
    if points < 10 or not user:
        return False
    u = get_user(user)
    if not u or u["points"] < points:
        return False
    change_points(user, -points, f"公益捐赠 {points} 积分")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO public_good (user, points, created_at) VALUES (?,?,?)''', (user, points, now))
    conn.commit()
    conn.close()
    add_medal(user, "公益大使", "❤️")
    add_exp(user, points//10)
    return True

def get_public_total() -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT SUM(points) FROM public_good")
    total = c.fetchone()[0] or 0
    conn.close()
    return total

# ==================== 管理员后台 ====================
def admin_get_all_users(page=1, page_size=20) -> List[Dict]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    offset = (page-1)*page_size
    c.execute("SELECT * FROM users ORDER BY id DESC LIMIT ? OFFSET ?", (page_size, offset))
    rows = c.fetchall()
    cols = [d[0] for d in c.description]
    conn.close()
    return [dict(zip(cols, r)) for r in rows]

def admin_get_all_videos(page=1, page_size=20) -> List[Dict]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    offset = (page-1)*page_size
    c.execute("SELECT * FROM videos ORDER BY id DESC LIMIT ? OFFSET ?", (page_size, offset))
    rows = c.fetchall()
    cols = [d[0] for d in c.description]
    conn.close()
    return [dict(zip(cols, r)) for r in rows]

def admin_get_all_orders(page=1, page_size=20) -> List[Dict]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    offset = (page-1)*page_size
    c.execute("SELECT * FROM orders ORDER BY id DESC LIMIT ? OFFSET ?", (page_size, offset))
    rows = c.fetchall()
    cols = [d[0] for d in c.description]
    conn.close()
    return [dict(zip(cols, r)) for r in rows]

def admin_get_all_withdraw(page=1, page_size=20) -> List[Dict]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    offset = (page-1)*page_size
    c.execute("SELECT * FROM withdraw ORDER BY id DESC LIMIT ? OFFSET ?", (page_size, offset))
    rows = c.fetchall()
    cols = [d[0] for d in c.description]
    conn.close()
    return [dict(zip(cols, r)) for r in rows]

def admin_deal_withdraw(wid: int, status: int, remark: str = "") -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("UPDATE withdraw SET status=?, deal_at=?, remark=? WHERE id=?", (status, now, remark, wid))
    conn.commit()
    conn.close()
    return True

def admin_update_video_status(vid: int, status: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE videos SET status=? WHERE id=?", (status, vid))
    conn.commit()
    conn.close()
    return True

def admin_update_user_status(uid: int, status: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET status=? WHERE id=?", (status, uid))
    conn.commit()
    conn.close()
    return True

def admin_update_user_vip(username: str, vip_level: int, days: int = 30) -> bool:
    expire = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET vip_level=?, vip_expire=? WHERE username=?", (vip_level, expire, username))
    conn.commit()
    conn.close()
    return True

def admin_get_statistics() -> Dict:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    stats = {}
    c.execute("SELECT COUNT(*) FROM users")
    stats["user_count"] = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM videos")
    stats["video_count"] = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM orders WHERE status=1")
    stats["order_count"] = c.fetchone()[0]
    c.execute("SELECT SUM(price) FROM orders WHERE status=1")
    stats["total_money"] = c.fetchone()[0] or 0
    c.execute("SELECT SUM(points) FROM public_good")
    stats["public_total"] = c.fetchone()[0] or 0
    conn.close()
    return stats

# ==================== 草稿保存（P0） ====================
def save_draft(user: str, name: str, params: dict) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    params_json = json.dumps(params)
    c.execute("SELECT id FROM drafts WHERE user=? AND name=?", (user, name))
    if c.fetchone():
        c.execute("UPDATE drafts SET params=?, updated_at=? WHERE user=? AND name=?", (params_json, now, user, name))
    else:
        c.execute("INSERT INTO drafts (user, name, params, created_at, updated_at) VALUES (?,?,?,?,?)",
                  (user, name, params_json, now, now))
    conn.commit()
    conn.close()
    return True

def load_draft(user: str, name: str) -> Optional[dict]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT params FROM drafts WHERE user=? AND name=?", (user, name))
    row = c.fetchone()
    conn.close()
    return json.loads(row[0]) if row else None

def list_drafts(user: str) -> List[str]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name FROM drafts WHERE user=? ORDER BY updated_at DESC", (user,))
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

# ==================== 免费素材库批量导入（P0） ====================
def import_materials_batch(folder_path: str, mat_type: str):
    if not os.path.exists(folder_path):
        return 0
    count = 0
    for f in os.listdir(folder_path):
        ext = f.split('.')[-1].lower()
        if mat_type == "video" and ext in ["mp4","mov","avi","mkv"]:
            name = os.path.splitext(f)[0]
            path = os.path.join(folder_path, f)
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("INSERT INTO materials (name, type, path, free) VALUES (?,?,?,1)", (name, mat_type, path))
            conn.commit()
            conn.close()
            count += 1
        elif mat_type == "audio" and ext in ["mp3","wav","flac"]:
            name = os.path.splitext(f)[0]
            path = os.path.join(folder_path, f)
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("INSERT INTO materials (name, type, path, free) VALUES (?,?,?,1)", (name, mat_type, path))
            conn.commit()
            conn.close()
            count += 1
    return count

def get_materials(mat_type: str = "video", free_only: bool = True) -> List[Dict]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if free_only:
        c.execute("SELECT * FROM materials WHERE type=? AND free=1", (mat_type,))
    else:
        c.execute("SELECT * FROM materials WHERE type=?", (mat_type,))
    rows = c.fetchall()
    cols = [d[0] for d in c.description]
    conn.close()
    return [dict(zip(cols, r)) for r in rows]

# ==================== 异步任务队列（简化版，使用线程） ====================
def add_task(user: str, task_type: str, params: dict) -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    params_json = json.dumps(params)
    c.execute('''INSERT INTO task_queue (user, task_type, params, status, created_at)
        VALUES (?,?,?,?,?)''', (user, task_type, params_json, "pending", now))
    task_id = c.lastrowid
    conn.commit()
    conn.close()
    # 启动后台线程处理
    thread = threading.Thread(target=_process_task, args=(task_id,))
    thread.daemon = True
    thread.start()
    return task_id

def _process_task(task_id: int):
    time.sleep(1)  # 模拟延迟
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT task_type, params FROM task_queue WHERE id=?", (task_id,))
    row = c.fetchone()
    if not row:
        return
    task_type, params_json = row
    params = json.loads(params_json)
    c.execute("UPDATE task_queue SET status='running' WHERE id=?", (task_id,))
    conn.commit()
    result_path = None
    error_msg = ""
    try:
        if task_type == "novel_to_video":
            novel = params.get("novel", "")
            style = params.get("style", "default")
            duration = params.get("duration", 60)
            result_path = ai_novel_to_video(novel, style, duration)
        elif task_type == "digital_human":
            text = params.get("text", "")
            style = params.get("style", "default")
            result_path = ai_digital_human(text, style)
        elif task_type == "novel_to_series":
            title = params.get("title", "")
            outline = params.get("outline", "")
            num = params.get("num_episodes", 2)
            dur = params.get("duration_per_episode", 60)
            style = params.get("style", "default")
            paths = ai_novel_to_series(title, outline, num, dur, style)
            result_path = json.dumps(paths) if paths else ""
        if result_path:
            c.execute("UPDATE task_queue SET status='completed', result_path=?, finished_at=? WHERE id=?", (result_path, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), task_id))
        else:
            error_msg = "生成失败"
            c.execute("UPDATE task_queue SET status='failed', error_msg=?, finished_at=? WHERE id=?", (error_msg, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), task_id))
    except Exception as e:
        error_msg = str(e)
        c.execute("UPDATE task_queue SET status='failed', error_msg=?, finished_at=? WHERE id=?", (error_msg, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), task_id))
    conn.commit()
    conn.close()

def get_task_status(task_id: int) -> Optional[Dict]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT status, result_path, error_msg FROM task_queue WHERE id=?", (task_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"status": row[0], "result_path": row[1], "error_msg": row[2]}
    return None

# ==================== 主界面 ====================
def main():
    if "user" not in st.session_state:
        st.session_state.user = None
    if "page" not in st.session_state:
        st.session_state.page = "首页"
    if "temp_video" not in st.session_state:
        st.session_state.temp_video = None
    if "task_id" not in st.session_state:
        st.session_state.task_id = None

    with st.sidebar:
        st.title("🤖 小智 v4.0")
        st.markdown("### 剪映 + 豆包 + 抖音 三合一")
        menu = option_menu(
            "主菜单",
            ["首页", "AI创作", "视频剪辑", "壁纸商城", "版图商城", "个人中心", "任务中心", "公益", "素材库", "管理员后台"],
            icons=["house", "robot", "film", "image", "palette", "person", "check2-circle", "heart", "database", "shield"],
            menu_icon="list",
            default_index=0,
            orientation="vertical"
        )
        st.session_state.page = menu

        user = st.session_state.user
        if user:
            uinfo = get_user(user)
            st.success(f"👤 欢迎：{uinfo.get('nickname', user)}")
            st.markdown(f"💰 积分：{uinfo.get('points', 0)}")
            st.markdown(f"⭐ 等级：Lv.{uinfo.get('level', 1)}")
            vip = uinfo.get("vip_level", 0)
            if vip > 0:
                st.markdown(f"🌟 VIP：{VIP_LEVEL[vip]}")
            if st.button("退出登录"):
                st.session_state.user = None
                st.rerun()
        else:
            st.info("请登录/注册")
            tab1, tab2, tab3 = st.tabs(["手机号登录", "用户名登录", "注册"])
            with tab1:
                phone = st.text_input("手机号", key="phone_login")
                code = st.text_input("验证码", key="sms_code")
                if st.button("获取验证码"):
                    fake_code = str(random.randint(100000, 999999))
                    st.session_state.verify_code = fake_code
                    st.success(f"【演示】验证码：{fake_code}")
                if st.button("登录/注册"):
                    if 'verify_code' in st.session_state and code == st.session_state.verify_code:
                        if not user_exists(phone):
                            register_user(phone, "123456", phone, phone)
                        st.session_state.user = phone
                        update_user_last_active(phone)
                        st.success("登录成功")
                        st.rerun()
                    else:
                        st.error("验证码错误")
            with tab2:
                login_user = st.text_input("用户名", key="login_user")
                login_pwd = st.text_input("密码", type="password", key="login_pwd")
                if st.button("登录", key="login_btn"):
                    if check_password(login_user, login_pwd):
                        st.session_state.user = login_user
                        update_user_last_active(login_user)
                        st.success("登录成功")
                        st.rerun()
                    else:
                        st.error("用户名或密码错误")
            with tab3:
                reg_user = st.text_input("用户名", key="reg_user")
                reg_pwd = st.text_input("密码", type="password", key="reg_pwd")
                reg_nick = st.text_input("昵称", key="reg_nick")
                reg_phone = st.text_input("手机号", key="reg_phone")
                if st.button("注册", key="reg_btn"):
                    if len(reg_user) < 3 or len(reg_pwd) < 6:
                        st.warning("用户名≥3，密码≥6")
                    elif register_user(reg_user, reg_pwd, reg_nick, reg_phone):
                        st.success("注册成功，请登录")
                    else:
                        st.error("用户名已存在")

    # 页面路由
    if st.session_state.page == "首页":
        st.title("首页 · 推荐")
        videos = get_videos(page=1, page_size=12)
        if not videos:
            st.info("暂无作品，快去创作吧！")
        else:
            cols = st.columns(3)
            for i, v in enumerate(videos):
                with cols[i % 3]:
                    st.image(v["cover_path"], use_column_width=True)
                    st.subheader(v["title"])
                    st.caption(f"作者：{v['user']} | 👀 {v['views']} | ❤️ {v['likes']}")
                    if st.button(f"观看", key=f"watch_{v['id']}"):
                        st.session_state.watch_vid = v["id"]
                        st.rerun()

    elif st.session_state.page == "AI创作":
        st.title("🤖 AI智能创作")
        ai_tab = st.selectbox("选择AI功能", ["AI文案生成", "AI文字转语音", "AI封面生成", "AI小说转视频", "AI小说转连续剧", "AI数字人播报", "AI智能配乐"])
        if ai_tab == "AI文案生成":
            topic = st.text_input("输入主题")
            length = st.radio("长度", ["短","中","长"], horizontal=True)
            if st.button("一键生成脚本"):
                script = ai_auto_script(topic, length)
                st.text_area("生成结果", script, height=300)
        elif ai_tab == "AI文字转语音":
            text = st.text_area("输入文字", height=200)
            if st.button("生成配音"):
                with st.spinner("生成中..."):
                    path = ai_text_to_speech(text)
                    if path:
                        st.success("完成")
                        st.audio(path)
        elif ai_tab == "AI封面生成":
            text = st.text_input("封面文字")
            style = st.selectbox("风格", ["default","cool","warm","fresh"])
            if st.button("生成封面"):
                with st.spinner("生成中..."):
                    path = ai_create_cover(text, style)
                    if path:
                        st.image(path)
        elif ai_tab == "AI小说转视频":
            novel = st.text_area("粘贴小说内容", height=300)
            style = st.selectbox("风格", ["default","cool","warm"])
            if st.button("生成视频"):
                with st.spinner("生成中..."):
                    path = ai_novel_to_video(novel, style, 60)
                    if path:
                        st.video(path)
        elif ai_tab == "AI小说转连续剧":
            title = st.text_input("连续剧标题")
            outline = st.text_area("剧情大纲", height=150)
            num_episodes = st.number_input("集数", 1, 10, 2)
            duration_per = st.number_input("每集时长(秒)", 30, 120, 60)
            style = st.selectbox("风格", ["default","cool","warm"])
            if st.button("生成连续剧"):
                if not st.session_state.user:
                    st.warning("请先登录")
                else:
                    task_id = add_task(st.session_state.user, "novel_to_series", {
                        "title": title, "outline": outline, "num_episodes": num_episodes,
                        "duration_per_episode": duration_per, "style": style
                    })
                    st.session_state.task_id = task_id
                    st.success(f"任务已提交，ID: {task_id}，请稍后到个人中心查看")
        elif ai_tab == "AI数字人播报":
            text = st.text_area("播报文案", height=200)
            style = st.selectbox("背景风格", ["default","office","studio"])
            if st.button("生成数字人视频"):
                with st.spinner("生成中..."):
                    path = ai_digital_human(text, style)
                    if path:
                        st.video(path)
        elif ai_tab == "AI智能配乐":
            mood = st.selectbox("情绪", ["happy","sad","excited","calm"])
            if st.button("推荐音乐"):
                music = ai_smart_music(mood)
                st.audio(music)

    elif st.session_state.page == "视频剪辑":
        st.title("🎬 专业视频剪辑")
        file = st.file_uploader("上传视频", type=["mp4","mov","avi"])
        if file:
            path = f"temp/{file.name}"
            with open(path, "wb") as f:
                f.write(file.getbuffer())
            st.session_state.temp_video = path
            st.video(path)
            # 草稿功能
            if st.session_state.user:
                draft_name = st.text_input("草稿名称", key="draft_name")
                if st.button("保存草稿"):
                    params = {"video_path": path, "name": file.name}
                    if save_draft(st.session_state.user, draft_name, params):
                        st.success("草稿已保存")
                drafts = list_drafts(st.session_state.user)
                if drafts:
                    selected_draft = st.selectbox("加载草稿", drafts)
                    if st.button("加载"):
                        params = load_draft(st.session_state.user, selected_draft)
                        if params:
                            st.session_state.temp_video = params.get("video_path")
                            st.rerun()
            tools = st.multiselect("剪辑工具", ["裁剪","变速","旋转","翻转","滤镜","字幕","水印","配乐","倒放","抠像","GIF导出"])
            if "裁剪" in tools:
                start = st.number_input("开始时间",0.0,600.0,0.0)
                end = st.number_input("结束时间",0.0,600.0,10.0)
                if st.button("执行裁剪"):
                    out = video_cut(path, start, end)
                    if out: st.video(out)
            if "滤镜" in tools:
                f = st.selectbox("选择滤镜", list(FILTERS.keys()))
                if st.button("应用滤镜"):
                    out = apply_filter(path, f)
                    if out: st.video(out)
            if "字幕" in tools:
                txt = st.text_input("字幕内容")
                pos = st.selectbox("位置", ["bottom","center","top"])
                if st.button("添加字幕"):
                    out = add_subtitle(path, txt, pos)
                    if out: st.video(out)
            if "配乐" in tools:
                audio = st.file_uploader("上传音乐", type=["mp3","wav"])
                vol = st.slider("音量",0.0,2.0,1.0)
                if audio and st.button("添加背景音乐"):
                    apath = f"temp/{audio.name}"
                    with open(apath,"wb") as f:
                        f.write(audio.getbuffer())
                    out = add_audio(path, apath, vol)
                    if out: st.video(out)

    elif st.session_state.page == "个人中心":
        if not st.session_state.user:
            st.warning("请先登录")
            return
        st.title("👤 个人中心")
        u = get_user(st.session_state.user)
        st.markdown(f"### 昵称：{u.get('nickname', '未设置')}")
        st.markdown(f"### 积分：{u.get('points', 0)}")
        st.markdown(f"### 等级：Lv.{u.get('level', 1)}")
        st.markdown(f"### 粉丝：{u.get('fans', 0)}")
        st.markdown(f"### 关注：{u.get('follows', 0)}")
        st.markdown(f"### VIP：{VIP_LEVEL.get(u.get('vip_level',0), '普通用户')}")
        medals = get_user_medals(st.session_state.user)
        if medals:
            st.markdown("### 🏅 我的勋章")
            cols = st.columns(4)
            for i, m in enumerate(medals):
                with cols[i%4]:
                    st.info(f"{m['icon']} {m['name']}")
        st.markdown("### 🎬 我的视频")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT * FROM videos WHERE user=? ORDER BY id DESC", (st.session_state.user,))
        vs = c.fetchall()
        conn.close()
        for v in vs:
            st.video(v[6])
            st.caption(v[2])
        # 任务进度
        if st.session_state.task_id:
            status = get_task_status(st.session_state.task_id)
            if status:
                if status["status"] == "completed":
                    st.success("AI任务完成！")
                    result = status["result_path"]
                    if result.startswith("["):
                        paths = json.loads(result)
                        for p in paths:
                            st.video(p)
                    else:
                        st.video(result)
                    st.session_state.task_id = None
                elif status["status"] == "failed":
                    st.error(f"任务失败：{status['error_msg']}")
                    st.session_state.task_id = None
                else:
                    st.info("任务处理中，请稍后刷新...")

    elif st.session_state.page == "任务中心":
        if not st.session_state.user:
            st.warning("请先登录")
            return
        st.title("✅ 任务中心")
        if st.button("每日签到"):
            if daily_task(st.session_state.user):
                st.success("签到成功 +20 积分")
            else:
                st.warning("今日已签到")
        st.markdown("### 可完成任务")
        st.info("发布视频 +50 积分")
        st.info("点赞评论 +10 积分")
        st.info("分享视频 +5 积分")
        tasks = get_user_tasks(st.session_state.user)
        if tasks:
            st.markdown("### 已完成任务")
            for t in tasks:
                st.success(f"{t['task_name']} +{t['reward']} 积分")

    elif st.session_state.page == "公益":
        st.title("❤️ 小智公益")
        total = get_public_total()
        st.markdown(f"## 全站公益积分：{total}")
        if st.session_state.user:
            points = st.number_input("捐赠积分", 10, 10000, 10)
            if st.button("确认捐赠"):
                if donate_public_good(st.session_state.user, points):
                    st.success(f"感谢捐赠 {points} 积分")
                else:
                    st.error("积分不足")
        st.markdown("### 公益记录")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT * FROM public_good ORDER BY id DESC LIMIT 20")
        records = c.fetchall()
        conn.close()
        for r in records:
            st.text(f"{r[1]} 捐赠 {r[2]} 积分")

    elif st.session_state.page == "素材库":
        st.title("📁 免费素材库")
        mat_type = st.selectbox("素材类型", ["video","audio"])
        if st.session_state.user and is_admin(st.session_state.user, 2):
            uploaded_files = st.file_uploader("批量上传素材", accept_multiple_files=True, type=["mp4","mov","mp3","wav"])
            if uploaded_files and st.button("导入素材库"):
                count = 0
                for file in uploaded_files:
                    ext = file.name.split('.')[-1].lower()
                    if mat_type == "video" and ext in ["mp4","mov"]:
                        path = f"materials_bulk/{file.name}"
                        with open(path, "wb") as f:
                            f.write(file.getbuffer())
                        conn = sqlite3.connect(DB_PATH)
                        c = conn.cursor()
                        c.execute("INSERT INTO materials (name, type, path, free) VALUES (?,?,?,1)", (file.name, mat_type, path))
                        conn.commit()
                        conn.close()
                        count += 1
                    elif mat_type == "audio" and ext in ["mp3","wav"]:
                        path = f"materials_bulk/{file.name}"
                        with open(path, "wb") as f:
                            f.write(file.getbuffer())
                        conn = sqlite3.connect(DB_PATH)
                        c = conn.cursor()
                        c.execute("INSERT INTO materials (name, type, path, free) VALUES (?,?,?,1)", (file.name, mat_type, path))
                        conn.commit()
                        conn.close()
                        count += 1
                st.success(f"成功导入 {count} 个素材")
        materials = get_materials(mat_type, free_only=True)
        if materials:
            for m in materials:
                st.markdown(f"**{m['name']}**")
                if mat_type == "video":
                    st.video(m["path"])
                else:
                    st.audio(m["path"])

    elif st.session_state.page == "管理员后台":
        if not is_admin(st.session_state.user):
            st.error("无权限")
            return
        st.title("🔧 管理员后台")
        admin_menu = st.selectbox("管理面板", ["数据概览","用户管理","视频管理","订单管理","提现管理","VIP管理"])
        if admin_menu == "数据概览":
            stats = admin_get_statistics()
            st.metric("总用户", stats["user_count"])
            st.metric("总视频", stats["video_count"])
            st.metric("总交易额", stats["total_money"])
            st.metric("公益总额", stats["public_total"])
        elif admin_menu == "用户管理":
            users = admin_get_all_users()
            for u in users:
                st.markdown(f"{u['username']} | Lv.{u['level']} | 积分：{u['points']}")
                if st.button(f"禁用 {u['username']}", key=f"u_{u['id']}"):
                    admin_update_user_status(u['id'], 0)
                    st.success("已禁用")
        elif admin_menu == "视频管理":
            vs = admin_get_all_videos()
            for v in vs:
                st.video(v["video_path"])
                st.caption(f"{v['user']} | {v['title']}")
                if st.button(f"下架", key=f"v_{v['id']}"):
                    admin_update_video_status(v['id'], 0)
                    st.success("已下架")

    clean_temp_files()

if __name__ == "__main__":
    main()
