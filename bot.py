import os
from dotenv import load_dotenv
import discord
from discord.ext import commands
import asyncio
from typing import cast

load_dotenv()
raw_token = os.getenv('DISCORD_TOKEN')
if not raw_token:
    raise ValueError("Le token Discord n'est pas défini dans le fichier .env.")
token: str = raw_token

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True

bot = commands.Bot(command_prefix='!', intents=intents)

async def load_cogs():
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            await bot.load_extension(f'cogs.{filename[:-3]}')

@bot.event
async def on_ready():
    print(f'Connecté en tant que {bot.user}!')
    await bot.tree.sync()

if __name__ == "__main__":
    async def main():
        await load_cogs()
        await bot.start(token)
    asyncio.run(main())
