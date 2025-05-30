import os
from dotenv import load_dotenv
import discord
from discord.ext import commands
from discord import app_commands

load_dotenv()  # charge le .env
token = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
bot = commands.Bot(command_prefix='!', intents=intents)
intents.message_content = True  # si tu lis le contenu des messages
intents.members = True          # si tu veux voir les membres du serveur
intents.presences = True        # si tu veux voir leur statut en ligne
tree = bot.tree

@bot.event
async def on_ready():
    print(f'Connecté en tant que {bot.user}!')
    await tree.sync()

@bot.command()
async def ping(ctx):
    await ctx.send('Pong!')

@tree.command(name="ping", description="Répond Pong!")
async def ping_slash(interaction: discord.Interaction):
    await interaction.response.send_message("Pong!")

bot.run(token)
