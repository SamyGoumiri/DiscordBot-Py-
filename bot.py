import os
from dotenv import load_dotenv
import discord
from discord.ext import commands

load_dotenv()  # charge le .env
token = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Connecté en tant que {bot.user}!')

@bot.command()
async def ping(ctx):
    await ctx.send('Pong!')

bot.run(token)
