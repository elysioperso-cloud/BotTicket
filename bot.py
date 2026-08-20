import json
import logging

import discord
from discord.ext import commands

from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Bot en ligne !"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("bot")

with open("config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

INTENTS = discord.Intents.default()
INTENTS.members = True  # nécessaire pour résoudre les membres (rôles, permissions)


class TicketBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=INTENTS, help_command=None)
        self.config = CONFIG

    async def setup_hook(self):
        await self.load_extension("cogs.tickets")

        guild_id = self.config.get("guild_id")
        if guild_id:
            guild = discord.Object(id=guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info(f"{len(synced)} commande(s) synchronisée(s) sur le serveur {guild_id}.")
        else:
            synced = await self.tree.sync()
            log.info(f"{len(synced)} commande(s) synchronisée(s) globalement.")

    async def on_ready(self):
        log.info(f"Connecté en tant que {self.user} (ID: {self.user.id})")
        log.info("Bot prêt.")


bot = TicketBot()

if __name__ == "__main__":
    if not CONFIG.get("token") or CONFIG["token"] == "VOTRE_TOKEN_DISCORD_ICI":
        raise SystemExit(
            "Merci de renseigner votre token Discord dans config.json avant de lancer le bot."
        )
        keep_alive() # Démarre le serveur web

    bot.run(CONFIG["token"])
