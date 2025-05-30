import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import time
from typing import Dict, Optional, Union
from PIL import Image, ImageDraw, ImageFont

XP_FILE = 'xp_data.json'
CONFIG_FILE = 'xp_config.json'

# Chargement et sauvegarde des données XP
class XPStorage:
    def __init__(self):
        self.data = self.load()

    def load(self) -> Dict:
        if os.path.exists(XP_FILE):
            with open(XP_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def save(self):
        with open(XP_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def add_xp(self, user_id: str, amount: int, mode: str) -> int:
        if user_id not in self.data:
            self.data[user_id] = {"text": 0, "voice": 0, "level": 1, "last_xp": 0}
        self.data[user_id][mode] += amount
        # Calcul du niveau (exponentiel)
        xp_total = self.data[user_id][mode]
        level = 1
        while xp_total >= 50 * (level ** 2):
            level += 1
        if level > self.data[user_id].get(f"{mode}_level", 1):
            self.data[user_id][f"{mode}_level"] = level
            self.save()
            return level  # Level up
        self.data[user_id][f"{mode}_level"] = level
        self.save()
        return 0  # Pas de level up

    def get_xp(self, user_id: str, mode: str) -> int:
        return self.data.get(user_id, {}).get(mode, 0)

    def get_level(self, user_id: str, mode: str) -> int:
        return self.data.get(user_id, {}).get(f"{mode}_level", 1)

    def get_leaderboard(self, mode: str):
        return sorted(self.data.items(), key=lambda x: x[1].get(mode, 0), reverse=True)

class ConfigStorage:
    def __init__(self):
        self.data = self.load()

    def load(self) -> Dict:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def save(self):
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def get_cooldown(self, guild_id: str) -> int:
        return self.data.get(guild_id, {}).get('cooldown', 30)

    def set_cooldown(self, guild_id: str, value: int):
        if guild_id not in self.data:
            self.data[guild_id] = {}
        self.data[guild_id]['cooldown'] = value
        self.save()

    def get_notify_channel(self, guild_id: str) -> Optional[int]:
        return self.data.get(guild_id, {}).get('notify_channel')

    def set_notify_channel(self, guild_id: str, channel_id: int):
        if guild_id not in self.data:
            self.data[guild_id] = {}
        self.data[guild_id]['notify_channel'] = channel_id
        self.save()

class XPCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.storage = XPStorage()
        self.config = ConfigStorage()
        self.voice_tracking = {}
        self.voice_xp_task.start()
        self.cooldowns = {}  # anti-spam XP
        self.levelup_roles = {5: 123456789012345678, 10: 234567890123456789}  # exemple: {niveau: role_id}

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
        now = time.time()
        user_id = str(message.author.id)
        guild_id = str(message.guild.id)
        cooldown = self.config.get_cooldown(guild_id)
        if user_id in self.cooldowns and now - self.cooldowns[user_id] < cooldown:
            return
        self.cooldowns[user_id] = now
        level_up = self.storage.add_xp(user_id, 5, "text")
        if level_up:
            notify_channel_id = self.config.get_notify_channel(guild_id)
            channel = message.guild.get_channel(notify_channel_id) if notify_channel_id else message.channel
            await channel.send(f"🎉 {message.author.mention} passe niveau {self.storage.get_level(user_id, 'text')} en texte !")
            # Attribution de rôle si palier atteint
            if level_up in self.levelup_roles:
                role = message.guild.get_role(self.levelup_roles[level_up])
                if role:
                    await message.author.add_roles(role)
                    await channel.send(f"{message.author.mention} a débloqué le rôle {role.mention} !")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return
        if after.channel and not before.channel:
            self.voice_tracking[member.id] = 0
        elif before.channel and not after.channel:
            self.voice_tracking.pop(member.id, None)

    @tasks.loop(minutes=1)
    async def voice_xp_task(self):
        for user_id in list(self.voice_tracking.keys()):
            self.storage.add_xp(str(user_id), 10, "voice")

    @app_commands.command(name="level", description="Affiche votre niveau et XP.")
    async def level_slash(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        if not interaction.guild:
            await interaction.response.send_message("Cette commande doit être utilisée dans un serveur.", ephemeral=True)
            return
        resolved_member = member or interaction.guild.get_member(interaction.user.id)
        if not resolved_member:
            await interaction.response.send_message("Impossible de trouver le membre.", ephemeral=True)
            return
        text_xp = self.storage.get_xp(str(resolved_member.id), "text")
        voice_xp = self.storage.get_xp(str(resolved_member.id), "voice")
        text_level = self.storage.get_level(str(resolved_member.id), "text")
        voice_level = self.storage.get_level(str(resolved_member.id), "voice")
        await interaction.response.send_message(f"{resolved_member.display_name} - Texte: {text_xp} XP (Niveau {text_level}) | Vocal: {voice_xp} XP (Niveau {voice_level})")

    @app_commands.command(name="scoreboard", description="Affiche le classement XP.")
    async def scoreboard_slash(self, interaction: discord.Interaction, mode: str = "text"):
        if mode not in ("text", "voice"):
            await interaction.response.send_message("Mode invalide. Utilisez 'text' ou 'voice'.", ephemeral=True)
            return
        leaderboard = self.storage.get_leaderboard(mode)[:10]
        msg = f"Top 10 XP {mode}:\n"
        for i, (user_id, data) in enumerate(leaderboard, 1):
            user = self.bot.get_user(int(user_id))
            name = user.name if user else user_id
            msg += f"{i}. {name}: {data[mode]} XP\n"
        await interaction.response.send_message(msg)

    @app_commands.command(name="setcooldown", description="Configure le cooldown anti-spam XP (en secondes)")
    @app_commands.checks.has_permissions(administrator=True)
    async def setcooldown_slash(self, interaction: discord.Interaction, seconds: int):
        if not interaction.guild:
            await interaction.response.send_message("Cette commande doit être utilisée dans un serveur.", ephemeral=True)
            return
        guild_id = str(interaction.guild.id)
        self.config.set_cooldown(guild_id, seconds)
        await interaction.response.send_message(f"Cooldown anti-spam XP défini à {seconds} secondes.")

    @app_commands.command(name="setnotif", description="Configure le salon de notification de level up")
    @app_commands.checks.has_permissions(administrator=True)
    async def setnotif_slash(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not interaction.guild:
            await interaction.response.send_message("Cette commande doit être utilisée dans un serveur.", ephemeral=True)
            return
        guild_id = str(interaction.guild.id)
        self.config.set_notify_channel(guild_id, channel.id)
        await interaction.response.send_message(f"Salon de notification défini sur {channel.mention}.")

    @app_commands.command(name="profile", description="Affiche une image de votre profil XP")
    async def profile_slash(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        if not interaction.guild:
            await interaction.response.send_message("Cette commande doit être utilisée dans un serveur.", ephemeral=True)
            return
        resolved_member = member or interaction.guild.get_member(interaction.user.id)
        if not resolved_member:
            await interaction.response.send_message("Impossible de trouver le membre.", ephemeral=True)
            return
        text_xp = self.storage.get_xp(str(resolved_member.id), "text")
        text_level = self.storage.get_level(str(resolved_member.id), "text")
        img = Image.new('RGB', (400, 100), color=(73, 109, 137))
        d = ImageDraw.Draw(img)
        font = ImageFont.load_default()
        d.text((10,10), f"{resolved_member.display_name}", font=font, fill=(255,255,0))
        d.text((10,40), f"Niveau: {text_level}", font=font, fill=(255,255,255))
        d.text((10,70), f"XP: {text_xp}", font=font, fill=(255,255,255))
        img_path = f"profile_{resolved_member.id}.png"
        img.save(img_path)
        with open(img_path, 'rb') as f:
            file = discord.File(f, filename=img_path)
            await interaction.response.send_message(file=file)
        os.remove(img_path)

async def setup(bot):
    await bot.add_cog(XPCog(bot))
