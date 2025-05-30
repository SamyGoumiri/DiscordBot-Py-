import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import time
from typing import Dict, Optional, Union
from PIL import Image, ImageDraw, ImageFont
import aiosqlite

from .xp_db import XPDatabase

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
            self.data[user_id] = {"text": 0, "voice": 0, "messages": 0, "voice_time": 0, "text_level": 1, "voice_level": 1}
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

    def add_message(self, user_id: str):
        if user_id not in self.data:
            self.data[user_id] = {"text": 0, "voice": 0, "messages": 0, "voice_time": 0, "text_level": 1, "voice_level": 1}
        self.data[user_id]["messages"] = self.data[user_id].get("messages", 0) + 1
        self.save()

    def add_voice_time(self, user_id: str, minutes: int):
        if user_id not in self.data:
            self.data[user_id] = {"text": 0, "voice": 0, "messages": 0, "voice_time": 0, "text_level": 1, "voice_level": 1}
        self.data[user_id]["voice_time"] = self.data[user_id].get("voice_time", 0) + minutes
        self.save()

    def get_xp(self, user_id: str, mode: str) -> int:
        return self.data.get(user_id, {}).get(mode, 0)

    def get_level(self, user_id: str, mode: str) -> int:
        return self.data.get(user_id, {}).get(f"{mode}_level", 1)

    def get_messages(self, user_id: str) -> int:
        return self.data.get(user_id, {}).get("messages", 0)

    def get_voice_time(self, user_id: str) -> int:
        return self.data.get(user_id, {}).get("voice_time", 0)

    def get_leaderboard(self, mode: str):
        if mode == "text":
            return sorted(self.data.items(), key=lambda x: x[1].get("text", 0), reverse=True)
        elif mode == "voice":
            return sorted(self.data.items(), key=lambda x: x[1].get("voice", 0), reverse=True)
        elif mode == "messages":
            return sorted(self.data.items(), key=lambda x: x[1].get("messages", 0), reverse=True)
        elif mode == "voice_time":
            return sorted(self.data.items(), key=lambda x: x[1].get("voice_time", 0), reverse=True)
        else:
            return []

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
        self.db = XPDatabase()
        self.voice_tracking = {}
        self.voice_xp_task.start()
        self.levelup_roles = {5: 123456789012345678, 10: 234567890123456789}  # exemple: {niveau: role_id}

    async def cog_load(self):
        await self.db.init()

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
        user_id = str(message.author.id)
        guild_id = str(message.guild.id)
        await self.db.add_message(user_id, guild_id)
        level_up = await self.db.add_xp(user_id, guild_id, 5, "text")
        await self.db.log_xp_history(user_id, guild_id, "text", 5)
        if level_up:
            notify_channel_id = await self.db.get_notify_channel(guild_id)
            channel = message.guild.get_channel(notify_channel_id) if notify_channel_id else message.channel
            await channel.send(f"🎉 {message.author.mention} passe niveau {await self.db.get_level(user_id, guild_id, 'text')} en texte !")
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
            self.voice_tracking[member.id] = str(member.guild.id)
        elif before.channel and not after.channel:
            self.voice_tracking.pop(member.id, None)

    @tasks.loop(minutes=1)
    async def voice_xp_task(self):
        for user_id in list(self.voice_tracking.keys()):
            guild_id = self.voice_tracking[user_id]
            await self.db.add_xp(str(user_id), guild_id, 10, "voice")
            await self.db.add_voice_time(str(user_id), guild_id, 1)
            await self.db.log_xp_history(str(user_id), guild_id, "voice", 10)

    @app_commands.command(name="notifyxp", description="Active ou désactive les notifications de level-up pour vous.")
    async def notifyxp_slash(self, interaction: discord.Interaction, enabled: bool):
        try:
            if not interaction.guild:
                await interaction.response.send_message("Cette commande doit être utilisée dans un serveur.", ephemeral=True)
                return
            user_id = str(interaction.user.id)
            guild_id = str(interaction.guild.id)
            await self.db.set_notify_enabled(user_id, guild_id, enabled)
            await interaction.response.send_message(f"Notifications de level-up {'activées' if enabled else 'désactivées'}.", ephemeral=True)
        except Exception as e:
            print(f"[notifyxp_slash] Erreur: {e}")
            await interaction.response.send_message("Erreur lors de la modification de vos notifications.", ephemeral=True)

    @app_commands.command(name="rank", description="Affiche votre rang dans le classement XP.")
    async def rank_slash(self, interaction: discord.Interaction, mode: str = "text", member: Optional[discord.Member] = None):
        try:
            if not interaction.guild:
                await interaction.response.send_message("Cette commande doit être utilisée dans un serveur.", ephemeral=True)
                return
            resolved_member = member or interaction.guild.get_member(interaction.user.id)
            if not resolved_member:
                await interaction.response.send_message("Impossible de trouver le membre.", ephemeral=True)
                return
            guild_id = str(interaction.guild.id)
            leaderboard = await self.db.get_leaderboard(guild_id, mode)
            user_id = str(resolved_member.id)
            rank = next((i+1 for i, (uid, _) in enumerate(leaderboard) if uid == user_id), None)
            if rank:
                await interaction.response.send_message(f"{resolved_member.display_name} est classé #{rank} en mode {mode}.")
            else:
                await interaction.response.send_message(f"{resolved_member.display_name} n'est pas classé dans le top {len(leaderboard)} en mode {mode}.")
        except Exception as e:
            print(f"[rank_slash] Erreur: {e}")
            await interaction.response.send_message("Erreur lors de la récupération du rang.", ephemeral=True)

    @app_commands.command(name="backupxp", description="Exporte la base de données XP.")
    @app_commands.checks.has_permissions(administrator=True)
    async def backupxp_slash(self, interaction: discord.Interaction):
        try:
            backup_path = f"xp_backup_{int(time.time())}.db"
            await self.db.backup(backup_path)
            if os.path.exists(backup_path):
                with open(backup_path, 'rb') as f:
                    file = discord.File(f, filename=backup_path)
                    await interaction.response.send_message("Backup de la base de données XP :", file=file, ephemeral=True)
                os.remove(backup_path)
            else:
                await interaction.response.send_message("Erreur lors de la création du backup.", ephemeral=True)
        except Exception as e:
            print(f"[backupxp_slash] Erreur: {e}")
            await interaction.response.send_message("Erreur lors de l'export de la base de données.", ephemeral=True)

    @app_commands.command(name="level", description="Affiche votre niveau et XP.")
    async def level_slash(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        try:
            if not interaction.guild:
                await interaction.response.send_message("Cette commande doit être utilisée dans un serveur.", ephemeral=True)
                return
            resolved_member = member or interaction.guild.get_member(interaction.user.id)
            if not resolved_member:
                await interaction.response.send_message("Impossible de trouver le membre.", ephemeral=True)
                return
            text_xp = await self.db.get_xp(str(resolved_member.id), str(interaction.guild.id), "text")
            voice_xp = await self.db.get_xp(str(resolved_member.id), str(interaction.guild.id), "voice")
            text_level = await self.db.get_level(str(resolved_member.id), str(interaction.guild.id), "text")
            voice_level = await self.db.get_level(str(resolved_member.id), str(interaction.guild.id), "voice")
            await interaction.response.send_message(f"{resolved_member.display_name} - Texte: {text_xp} XP (Niveau {text_level}) | Vocal: {voice_xp} XP (Niveau {voice_level})")
        except Exception as e:
            print(f"[level_slash] Erreur: {e}")
            await interaction.response.send_message("Erreur lors de la récupération du niveau.", ephemeral=True)

    @app_commands.command(name="profile", description="Affiche une image de votre profil XP")
    async def profile_slash(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        try:
            if not interaction.guild:
                await interaction.response.send_message("Cette commande doit être utilisée dans un serveur.", ephemeral=True)
                return
            resolved_member = member or interaction.guild.get_member(interaction.user.id)
            if not resolved_member:
                await interaction.response.send_message("Impossible de trouver le membre.", ephemeral=True)
                return
            text_xp = await self.db.get_xp(str(resolved_member.id), str(interaction.guild.id), "text")
            text_level = await self.db.get_level(str(resolved_member.id), str(interaction.guild.id), "text")
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
        except Exception as e:
            print(f"[profile_slash] Erreur: {e}")
            await interaction.response.send_message("Erreur lors de la génération du profil.", ephemeral=True)

    @app_commands.command(name="scoreboard", description="Affiche le classement XP/messages/vocal.")
    async def scoreboard_slash(self, interaction: discord.Interaction, mode: str = "text"):
        try:
            if not interaction.guild:
                await interaction.response.send_message("Cette commande doit être utilisée dans un serveur.", ephemeral=True)
                return
            if mode not in ("text", "voice", "messages", "voice_time"):
                await interaction.response.send_message("Mode invalide. Utilisez 'text', 'voice', 'messages' ou 'voice_time'.", ephemeral=True)
                return
            guild_id = str(interaction.guild.id)
            leaderboard = await self.db.get_leaderboard(guild_id, mode)
            if mode == "messages":
                msg = f"Top 10 Messages :\n"
                for i, (user_id, value) in enumerate(leaderboard, 1):
                    user = self.bot.get_user(int(user_id))
                    name = user.name if user else user_id
                    msg += f"{i}. {name}: {value} messages\n"
            elif mode == "voice_time":
                msg = f"Top 10 Vocal (heures) :\n"
                for i, (user_id, value) in enumerate(leaderboard, 1):
                    user = self.bot.get_user(int(user_id))
                    name = user.name if user else user_id
                    hours = round(value / 60, 2)
                    msg += f"{i}. {name}: {hours} heures\n"
            elif mode == "text":
                msg = f"Top 10 XP Texte :\n"
                for i, (user_id, value) in enumerate(leaderboard, 1):
                    user = self.bot.get_user(int(user_id))
                    name = user.name if user else user_id
                    msg += f"{i}. {name}: {value} XP\n"
            elif mode == "voice":
                msg = f"Top 10 XP Vocal :\n"
                for i, (user_id, value) in enumerate(leaderboard, 1):
                    user = self.bot.get_user(int(user_id))
                    name = user.name if user else user_id
                    msg += f"{i}. {name}: {value} XP\n"
            await interaction.response.send_message(msg)
        except Exception as e:
            print(f"[scoreboard_slash] Erreur: {e}")
            await interaction.response.send_message("Erreur lors de la récupération du classement.", ephemeral=True)

    @app_commands.command(name="setcooldown", description="Configure le cooldown anti-spam XP (en secondes)")
    @app_commands.checks.has_permissions(administrator=True)
    async def setcooldown_slash(self, interaction: discord.Interaction, seconds: int):
        if not interaction.guild:
            await interaction.response.send_message("Cette commande doit être utilisée dans un serveur.", ephemeral=True)
            return
        guild_id = str(interaction.guild.id)
        await self.db.set_cooldown(guild_id, seconds)
        await interaction.response.send_message(f"Cooldown anti-spam XP défini à {seconds} secondes.")

    @app_commands.command(name="setnotif", description="Configure le salon de notification de level up")
    @app_commands.checks.has_permissions(administrator=True)
    async def setnotif_slash(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not interaction.guild:
            await interaction.response.send_message("Cette commande doit être utilisée dans un serveur.", ephemeral=True)
            return
        guild_id = str(interaction.guild.id)
        await self.db.set_notify_channel(guild_id, channel.id)
        await interaction.response.send_message(f"Salon de notification défini sur {channel.mention}.")

    @app_commands.command(name="xp", description="Informations sur le système d'XP.")
    async def xpinfo_slash(self, interaction: discord.Interaction):
        xp_text = (
            "**Système d'XP et de niveaux :**\n"
            "- Gagnez de l'XP texte en discutant sur le serveur.\n"
            "- Gagnez de l'XP vocal en restant en vocal.\n"
            "- Un cooldown anti-spam limite l'XP toutes les X secondes.\n"
            "- Des rôles spéciaux sont attribués à certains niveaux.\n"
            "- Utilisez /level, /scoreboard, /profile pour suivre votre progression !"
        )
        await interaction.response.send_message(xp_text, ephemeral=True)

    @app_commands.command(name="help", description="Affiche l'aide du bot.")
    async def help_slash(self, interaction: discord.Interaction):
        help_text = (
            "**Commandes principales : **\n"
            "/level [membre] — Affiche le niveau et l'XP d'un membre.\n"
            "/scoreboard [text|voice|messages|voice_time] — Affiche le classement XP/messages/vocal.\n"
            "/profile [membre] — Affiche une image de profil XP.\n"
            "/xp — Informations sur le système d'XP.\n"
            "/setcooldown <secondes> — Configure le cooldown anti-spam XP (admin).\n"
            "/setnotif <salon> — Configure le salon de notification de level up (admin).\n"
        )
        await interaction.response.send_message(help_text, ephemeral=True)

    @app_commands.command(name="resetxp", description="Réinitialise l'XP d'un utilisateur (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def resetxp_slash(self, interaction: discord.Interaction, member: discord.Member, confirmation: Optional[str] = None):
        try:
            if not interaction.guild:
                await interaction.response.send_message("Cette commande doit être utilisée dans un serveur.", ephemeral=True)
                return
            if confirmation != "oui":
                await interaction.response.send_message(f"⚠️ Cette action va supprimer définitivement l'XP de {member.display_name}.\nPour confirmer, relancez la commande avec le paramètre confirmation=oui.", ephemeral=True)
                return
            user_id = str(member.id)
            guild_id = str(interaction.guild.id)
            await self.db.reset_user(user_id, guild_id)
            await interaction.response.send_message(f"XP de {member.display_name} réinitialisé.", ephemeral=True)
        except Exception as e:
            print(f"[resetxp_slash] Erreur: {e}")
            await interaction.response.send_message("Erreur lors de la réinitialisation de l'XP.", ephemeral=True)

    @app_commands.command(name="xphistory", description="Affiche l'évolution de l'XP d'un utilisateur.")
    async def xphistory_slash(self, interaction: discord.Interaction, member: Optional[discord.Member] = None, mode: Optional[str] = None):
        try:
            if not interaction.guild:
                await interaction.response.send_message("Cette commande doit être utilisée dans un serveur.", ephemeral=True)
                return
            resolved_member = member or interaction.guild.get_member(interaction.user.id)
            if not resolved_member:
                await interaction.response.send_message("Impossible de trouver le membre.", ephemeral=True)
                return
            user_id = str(resolved_member.id)
            guild_id = str(interaction.guild.id)
            history = await self.db.get_xp_history(user_id, guild_id, mode)
            if not history:
                await interaction.response.send_message("Aucun historique d'XP trouvé.", ephemeral=True)
                return
            msg = f"Historique XP de {resolved_member.display_name} :\n"
            for amount, timestamp, mode_str in history:
                from datetime import datetime
                dt = datetime.fromtimestamp(timestamp)
                msg += f"[{dt.strftime('%Y-%m-%d %H:%M')}] +{amount} XP ({mode_str})\n"
            await interaction.response.send_message(msg, ephemeral=True)
        except Exception as e:
            print(f"[xphistory_slash] Erreur: {e}")
            await interaction.response.send_message("Erreur lors de la récupération de l'historique.", ephemeral=True)

async def setup(bot):
    cog = XPCog(bot)
    await cog.cog_load()
    await bot.add_cog(cog)
