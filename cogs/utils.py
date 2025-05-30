import discord
from discord.ext import commands
from discord import app_commands

class Utils(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Répond Pong!")
    async def ping_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message("Pong!")

async def setup(bot):
    await bot.add_cog(Utils(bot))
