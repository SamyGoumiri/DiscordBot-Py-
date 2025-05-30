import aiosqlite
import asyncio
from typing import Optional, List, Tuple
from discord.ext import commands

DB_PATH = 'xp_data.db'

class XPDatabase(commands.Cog):
    def __init__(self, bot, db_path=DB_PATH):
        self.bot = bot
        self.db_path = db_path

    async def init(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''CREATE TABLE IF NOT EXISTS xp (
                user_id TEXT,
                guild_id TEXT,
                text_xp INTEGER DEFAULT 0,
                voice_xp INTEGER DEFAULT 0,
                messages INTEGER DEFAULT 0,
                voice_time INTEGER DEFAULT 0,
                text_level INTEGER DEFAULT 1,
                voice_level INTEGER DEFAULT 1,
                notify_enabled INTEGER DEFAULT 1,
                PRIMARY KEY (user_id, guild_id)
            )''')
            await db.execute('''CREATE TABLE IF NOT EXISTS config (
                guild_id TEXT PRIMARY KEY,
                cooldown INTEGER DEFAULT 30,
                notify_channel INTEGER
            )''')
            await db.commit()

    async def add_message(self, user_id: str, guild_id: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''INSERT INTO xp (user_id, guild_id, messages) VALUES (?, ?, 1)
                ON CONFLICT(user_id, guild_id) DO UPDATE SET messages=messages+1''', (user_id, guild_id))
            await db.commit()

    async def add_voice_time(self, user_id: str, guild_id: str, minutes: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''INSERT INTO xp (user_id, guild_id, voice_time) VALUES (?, ?, ?)
                ON CONFLICT(user_id, guild_id) DO UPDATE SET voice_time=voice_time+?''', (user_id, guild_id, minutes, minutes))
            await db.commit()

    async def add_xp(self, user_id: str, guild_id: str, amount: int, mode: str) -> int:
        col = 'text_xp' if mode == 'text' else 'voice_xp'
        col_lvl = 'text_level' if mode == 'text' else 'voice_level'
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(f'''INSERT INTO xp (user_id, guild_id, {col}) VALUES (?, ?, ?)
                ON CONFLICT(user_id, guild_id) DO UPDATE SET {col}={col}+?''', (user_id, guild_id, amount, amount))
            # Calcul du niveau
            cursor = await db.execute(f'SELECT {col} FROM xp WHERE user_id=? AND guild_id=?', (user_id, guild_id))
            row = await cursor.fetchone()
            xp_total = row[0] if row and row[0] is not None else 0
            level = 1
            while xp_total >= 50 * (level ** 2):
                level += 1
            cursor = await db.execute(f'SELECT {col_lvl} FROM xp WHERE user_id=? AND guild_id=?', (user_id, guild_id))
            row_lvl = await cursor.fetchone()
            old_level = row_lvl[0] if row_lvl and row_lvl[0] is not None else 1
            await db.execute(f'UPDATE xp SET {col_lvl}=? WHERE user_id=? AND guild_id=?', (level, user_id, guild_id))
            await db.commit()
            return level if level > old_level else 0

    async def get_notify_channel(self, guild_id: str) -> Optional[int]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT notify_channel FROM config WHERE guild_id=?', (guild_id,))
            row = await cursor.fetchone()
            return row[0] if row and row[0] is not None else None

    async def set_notify_channel(self, guild_id: str, channel_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''INSERT INTO config (guild_id, notify_channel) VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET notify_channel=?''', (guild_id, channel_id, channel_id))
            await db.commit()

    async def get_cooldown(self, guild_id: str) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT cooldown FROM config WHERE guild_id=?', (guild_id,))
            row = await cursor.fetchone()
            return row[0] if row and row[0] is not None else 30

    async def set_cooldown(self, guild_id: str, value: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''INSERT INTO config (guild_id, cooldown) VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET cooldown=?''', (guild_id, value, value))
            await db.commit()

    async def get_xp(self, user_id: str, guild_id: str, mode: str) -> int:
        col = 'text_xp' if mode == 'text' else 'voice_xp'
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(f'SELECT {col} FROM xp WHERE user_id=? AND guild_id=?', (user_id, guild_id))
            row = await cursor.fetchone()
            return row[0] if row and row[0] is not None else 0

    async def get_level(self, user_id: str, guild_id: str, mode: str) -> int:
        col = 'text_level' if mode == 'text' else 'voice_level'
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(f'SELECT {col} FROM xp WHERE user_id=? AND guild_id=?', (user_id, guild_id))
            row = await cursor.fetchone()
            return row[0] if row and row[0] is not None else 1

    async def get_messages(self, user_id: str, guild_id: str) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT messages FROM xp WHERE user_id=? AND guild_id=?', (user_id, guild_id))
            row = await cursor.fetchone()
            return row[0] if row and row[0] is not None else 0

    async def get_voice_time(self, user_id: str, guild_id: str) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT voice_time FROM xp WHERE user_id=? AND guild_id=?', (user_id, guild_id))
            row = await cursor.fetchone()
            return row[0] if row and row[0] is not None else 0

    async def get_leaderboard(self, guild_id: str, mode: str, limit: int = 10) -> List[Tuple[str, int]]:
        col = {
            'text': 'text_xp',
            'voice': 'voice_xp',
            'messages': 'messages',
            'voice_time': 'voice_time'
        }.get(mode, 'text_xp')
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(f'SELECT user_id, {col} FROM xp WHERE guild_id=? ORDER BY {col} DESC LIMIT ?', (guild_id, limit))
            rows = await cursor.fetchall()
            return [(row[0], row[1]) for row in rows]

    async def set_notify_enabled(self, user_id: str, guild_id: str, enabled: bool):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''INSERT INTO xp (user_id, guild_id, notify_enabled) VALUES (?, ?, ?)
                ON CONFLICT(user_id, guild_id) DO UPDATE SET notify_enabled=?''', (user_id, guild_id, int(enabled), int(enabled)))
            await db.commit()

    async def get_notify_enabled(self, user_id: str, guild_id: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT notify_enabled FROM xp WHERE user_id=? AND guild_id=?', (user_id, guild_id))
            row = await cursor.fetchone()
            return bool(row[0]) if row else True

    async def backup(self, backup_path: str):
        import shutil
        shutil.copyfile(self.db_path, backup_path)

    async def import_db(self, import_path: str):
        import shutil
        shutil.copyfile(import_path, self.db_path)

    # Suggestion d'amélioration : reset XP d'un utilisateur
    async def reset_user(self, user_id: str, guild_id: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('DELETE FROM xp WHERE user_id=? AND guild_id=?', (user_id, guild_id))
            await db.commit()

    async def log_xp_history(self, user_id: str, guild_id: str, mode: str, amount: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''CREATE TABLE IF NOT EXISTS xp_history (
                user_id TEXT,
                guild_id TEXT,
                mode TEXT,
                amount INTEGER,
                timestamp INTEGER
            )''')
            import time
            await db.execute('INSERT INTO xp_history (user_id, guild_id, mode, amount, timestamp) VALUES (?, ?, ?, ?, ?)',
                             (user_id, guild_id, mode, amount, int(time.time())))
            await db.commit()

    async def get_xp_history(self, user_id: str, guild_id: str, mode: Optional[str] = None, limit: int = 20):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''CREATE TABLE IF NOT EXISTS xp_history (
                user_id TEXT,
                guild_id TEXT,
                mode TEXT,
                amount INTEGER,
                timestamp INTEGER
            )''')
            if mode:
                cursor = await db.execute('SELECT amount, timestamp, mode FROM xp_history WHERE user_id=? AND guild_id=? AND mode=? ORDER BY timestamp DESC LIMIT ?',
                                          (user_id, guild_id, mode, limit))
            else:
                cursor = await db.execute('SELECT amount, timestamp, mode FROM xp_history WHERE user_id=? AND guild_id=? ORDER BY timestamp DESC LIMIT ?',
                                          (user_id, guild_id, limit))
            rows = await cursor.fetchall()
            return [(row[0], row[1], row[2]) for row in rows] if rows else []

async def setup(bot):
    await bot.add_cog(XPDatabase(bot))
