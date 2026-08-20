import datetime
import io
import json
import os
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "tickets.json")

TICKET_TYPES = {
    "general": {"prefix": "ticket"},
    "bug": {"prefix": "bug"},
    "sanction": {"prefix": "sanction"},
}


# --------------------------------------------------------------------------
# Petite base de données JSON pour suivre les tickets ouverts
# --------------------------------------------------------------------------
class TicketStore:
    def __init__(self, path: str = DATA_PATH):
        self.path = path
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        if not os.path.exists(self.path):
            self._write({})

    def _read(self) -> dict:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _write(self, data: dict):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get(self, channel_id: int) -> Optional[dict]:
        return self._read().get(str(channel_id))

    def set(self, channel_id: int, **fields):
        data = self._read()
        entry = data.get(str(channel_id), {})
        entry.update(fields)
        data[str(channel_id)] = entry
        self._write(data)

    def create(self, channel_id: int, opener_id: int, ticket_type: str):
        self.set(channel_id, opener_id=opener_id, type=ticket_type, claimed_by=None, closed=False)

    def delete(self, channel_id: int):
        data = self._read()
        data.pop(str(channel_id), None)
        self._write(data)


# --------------------------------------------------------------------------
# Helpers de permissions
# --------------------------------------------------------------------------
def is_support_member(member: discord.Member, support_role_ids: list) -> bool:
    if member.guild_permissions.administrator:
        return True
    if member.guild_permissions.kick_members:
        return True
    member_role_ids = {r.id for r in member.roles}
    return bool(member_role_ids.intersection(support_role_ids))


def support_roles_mentions(guild: discord.Guild, support_role_ids: list) -> str:
    mentions = []
    for rid in support_role_ids:
        role = guild.get_role(rid)
        if role:
            mentions.append(role.mention)
    return ", ".join(mentions) if mentions else "les rôles Support"


# --------------------------------------------------------------------------
# Vue persistante : panneau de création de tickets (/ticket panel)
# --------------------------------------------------------------------------
class TicketPanelView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot
        e = bot.config["emojis"]

        buttons = [
            ("Ouvrir un ticket", discord.ButtonStyle.green, e["iron_golem"], "ticket_open_general", "general"),
            ("Rapport de bug", discord.ButtonStyle.gray, e["bug"], "ticket_open_bug", "bug"),
            ("Contestation de sanction", discord.ButtonStyle.gray, e["staff"], "ticket_open_sanction", "sanction"),
        ]
        for label, style, emoji, custom_id, ticket_type in buttons:
            button = discord.ui.Button(label=label, style=style, emoji=emoji, custom_id=custom_id)
            button.callback = self._make_callback(ticket_type)
            self.add_item(button)

    def _make_callback(self, ticket_type: str):
        async def callback(interaction: discord.Interaction):
            cog = self.bot.get_cog("Tickets")
            await cog.create_ticket(interaction, ticket_type)

        return callback


# --------------------------------------------------------------------------
# Vue persistante : gestion d'un ticket (Claim / Close / Réouvrir / Supprimer)
# --------------------------------------------------------------------------
class TicketManageView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot
        e = bot.config["emojis"]

        claim_btn = discord.ui.Button(label="Claim", style=discord.ButtonStyle.blurple, emoji=e["notepad"], custom_id="ticket_claim")
        close_btn = discord.ui.Button(label="Close", style=discord.ButtonStyle.gray, emoji=e["hand"], custom_id="ticket_close")
        reopen_btn = discord.ui.Button(label="Réouvrir", style=discord.ButtonStyle.green, emoji=e["golden"], custom_id="ticket_reopen")
        delete_btn = discord.ui.Button(label="Supprimer", style=discord.ButtonStyle.red, emoji=e["know"], custom_id="ticket_delete")

        claim_btn.callback = self._claim
        close_btn.callback = self._close
        reopen_btn.callback = self._reopen
        delete_btn.callback = self._delete

        for b in (claim_btn, close_btn, reopen_btn, delete_btn):
            self.add_item(b)

    async def _claim(self, interaction: discord.Interaction):
        await self.bot.get_cog("Tickets").claim_ticket(interaction)

    async def _close(self, interaction: discord.Interaction):
        await self.bot.get_cog("Tickets").close_ticket(interaction)

    async def _reopen(self, interaction: discord.Interaction):
        await self.bot.get_cog("Tickets").reopen_ticket(interaction)

    async def _delete(self, interaction: discord.Interaction):
        await self.bot.get_cog("Tickets").delete_ticket(interaction)


# --------------------------------------------------------------------------
# Cog principal
# --------------------------------------------------------------------------
class Tickets(commands.Cog):
    ticket_group = app_commands.Group(name="ticket", description="Gestion du système de tickets")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cfg = bot.config
        self.store = TicketStore()

    async def cog_load(self):
        # Réenregistre les vues persistantes au (re)démarrage du bot
        self.bot.add_view(TicketPanelView(self.bot))
        self.bot.add_view(TicketManageView(self.bot))

    # ----------------------------------------------------------------
    # Commandes slash
    # ----------------------------------------------------------------
    @ticket_group.command(name="panel", description="Envoie le panneau de création de tickets dans un salon.")
    @app_commands.describe(salon="Salon où envoyer le panneau de tickets")
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_panel(self, interaction: discord.Interaction, salon: discord.TextChannel):
        e = self.cfg["emojis"]
        embed = discord.Embed(
            title=f"Support Ticket {e['world']}",
            description=(
                f"Comment pouvons nous vous aider ? {e['villager']}\n"
                "Utilisez l'un des boutons ci dessous pour contactez l'équipes, "
                "elle vous répondra aux plus vite!"
            ),
            color=discord.Color.blurple(),
        )
        view = TicketPanelView(self.bot)
        await salon.send(embed=embed, view=view)
        await interaction.response.send_message(f"✅ Panneau envoyé dans {salon.mention}.", ephemeral=True)

    @ticket_group.command(name="add", description="Ajoute un membre au ticket en cours.")
    @app_commands.describe(membre="Membre à ajouter au ticket")
    async def ticket_add(self, interaction: discord.Interaction, membre: discord.Member):
        channel = interaction.channel
        entry = self.store.get(channel.id)
        if entry is None:
            await interaction.response.send_message(
                "❌ Cette commande ne peut être utilisée que dans un salon de ticket.", ephemeral=True
            )
            return

        support_role_ids = self.cfg["support_role_ids"]
        is_opener = interaction.user.id == entry["opener_id"]
        if not (is_opener or is_support_member(interaction.user, support_role_ids)):
            mentions = support_roles_mentions(interaction.guild, support_role_ids)
            await interaction.response.send_message(
                f"❌ Seuls {mentions}, les administrateurs ou l'auteur du ticket peuvent ajouter un membre.",
                ephemeral=True,
            )
            return

        await channel.set_permissions(membre, view_channel=True, send_messages=True, read_message_history=True)
        await interaction.response.send_message(f"✅ {membre.mention} a été ajouté au ticket.")

    # ----------------------------------------------------------------
    # Logique métier (appelée par les boutons ET réutilisable)
    # ----------------------------------------------------------------
    async def create_ticket(self, interaction: discord.Interaction, ticket_type: str):
        guild = interaction.guild
        category = guild.get_channel(self.cfg["ticket_category_id"])
        if category is None or not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message(
                "❌ Catégorie de tickets introuvable. Contactez un administrateur.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        support_role_ids = self.cfg["support_role_ids"]
        prefix = TICKET_TYPES[ticket_type]["prefix"]
        safe_name = "".join(c for c in interaction.user.name.lower() if c.isalnum()) or "user"
        channel_name = f"{prefix}-{safe_name}"

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True,
                attach_files=True, embed_links=True,
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, manage_channels=True,
                manage_permissions=True, read_message_history=True,
            ),
        }
        for rid in support_role_ids:
            role = guild.get_role(rid)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True,
                    read_message_history=True, manage_messages=True,
                )

        channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            topic=f"Ticket de {interaction.user} ({interaction.user.id}) — type: {ticket_type}",
            reason=f"Ouverture de ticket par {interaction.user} ({interaction.user.id})",
        )

        self.store.create(channel.id, interaction.user.id, ticket_type)

        e = self.cfg["emojis"]
        embed = discord.Embed(
            title="Ticket",
            description=(
                f"Bienvenue dans votre ticket {e['discord']} !\n"
                "Veuillez fournir toute informations supplémentaires pour nous aider "
                "à répondre rapidement à votre demande."
            ),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text=f"Un staff arrivera dans les bref délai {e['loading']} !")

        mentions = support_roles_mentions(guild, support_role_ids)
        manage_view = TicketManageView(self.bot)
        msg = await channel.send(
            content=f"{mentions} | {interaction.user.mention}", embed=embed, view=manage_view
        )
        try:
            await msg.pin()
        except discord.HTTPException:
            pass

        await interaction.followup.send(f"✅ Votre ticket a été créé : {channel.mention}", ephemeral=True)

    async def claim_ticket(self, interaction: discord.Interaction):
        entry = self.store.get(interaction.channel.id)
        if entry is None:
            await interaction.response.send_message("❌ Ce salon n'est pas un ticket valide.", ephemeral=True)
            return

        support_role_ids = self.cfg["support_role_ids"]
        if not is_support_member(interaction.user, support_role_ids):
            mentions = support_roles_mentions(interaction.guild, support_role_ids)
            await interaction.response.send_message(
                f"❌ Seuls {mentions} ou les administrateurs peuvent claim ce ticket.", ephemeral=True
            )
            return

        self.store.set(interaction.channel.id, claimed_by=interaction.user.id)
        await interaction.response.send_message(f"{interaction.user.mention} a claim ce ticket")

    async def close_ticket(self, interaction: discord.Interaction):
        channel = interaction.channel
        entry = self.store.get(channel.id)
        if entry is None:
            await interaction.response.send_message("❌ Ce salon n'est pas un ticket valide.", ephemeral=True)
            return

        support_role_ids = self.cfg["support_role_ids"]
        is_opener = interaction.user.id == entry["opener_id"]
        if not (is_opener or is_support_member(interaction.user, support_role_ids)):
            mentions = support_roles_mentions(interaction.guild, support_role_ids)
            await interaction.response.send_message(
                f"❌ Seuls {mentions}, les administrateurs ou l'auteur du ticket peuvent fermer ce ticket.",
                ephemeral=True,
            )
            return

        opener = interaction.guild.get_member(entry["opener_id"])
        if opener:
            await channel.set_permissions(opener, send_messages=False)
        await channel.set_permissions(interaction.guild.default_role, view_channel=False)

        self.store.set(channel.id, closed=True)
        await interaction.response.send_message("🔒 Ticket fermé. Seul le staff peut désormais écrire ici.")

    async def reopen_ticket(self, interaction: discord.Interaction):
        channel = interaction.channel
        entry = self.store.get(channel.id)
        if entry is None:
            await interaction.response.send_message("❌ Ce salon n'est pas un ticket valide.", ephemeral=True)
            return

        support_role_ids = self.cfg["support_role_ids"]
        is_opener = interaction.user.id == entry["opener_id"]
        if not (is_opener or is_support_member(interaction.user, support_role_ids)):
            mentions = support_roles_mentions(interaction.guild, support_role_ids)
            await interaction.response.send_message(
                f"❌ Seuls {mentions}, les administrateurs ou l'auteur du ticket peuvent réouvrir ce ticket.",
                ephemeral=True,
            )
            return

        opener = interaction.guild.get_member(entry["opener_id"])
        if opener:
            await channel.set_permissions(opener, view_channel=True, send_messages=True, read_message_history=True)

        self.store.set(channel.id, closed=False)
        await interaction.response.send_message("🔓 Ticket réouvert.")

    async def delete_ticket(self, interaction: discord.Interaction):
        channel = interaction.channel
        entry = self.store.get(channel.id)
        if entry is None:
            await interaction.response.send_message("❌ Ce salon n'est pas un ticket valide.", ephemeral=True)
            return

        support_role_ids = self.cfg["support_role_ids"]
        if not is_support_member(interaction.user, support_role_ids):
            mentions = support_roles_mentions(interaction.guild, support_role_ids)
            await interaction.response.send_message(
                f"❌ Seuls {mentions} ou les administrateurs peuvent supprimer ce ticket.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            "🗑️ Suppression du ticket et génération du transcript en cours...", ephemeral=True
        )

        transcript_lines = []
        async for message in channel.history(limit=None, oldest_first=True):
            ts = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
            author = f"{message.author} ({message.author.id})"
            content = message.content or ""
            if message.attachments:
                attachments = ", ".join(a.url for a in message.attachments)
                content = f"{content} [Pièces jointes: {attachments}]".strip()
            transcript_lines.append(f"[{ts}] {author}: {content}")

        transcript_text = "\n".join(transcript_lines) if transcript_lines else "Aucun message dans ce ticket."
        transcript_file = discord.File(
            io.BytesIO(transcript_text.encode("utf-8")),
            filename=f"transcript-{channel.name}.txt",
        )

        transcript_channel = interaction.guild.get_channel(self.cfg["transcript_channel_id"])
        if transcript_channel:
            opener = interaction.guild.get_member(entry["opener_id"])
            summary = discord.Embed(
                title="Transcript de ticket",
                description=(
                    f"**Salon :** {channel.name}\n"
                    f"**Ouvert par :** {opener.mention if opener else entry['opener_id']}\n"
                    f"**Type :** {entry.get('type', 'inconnu')}\n"
                    f"**Fermé par :** {interaction.user.mention}"
                ),
                color=discord.Color.red(),
                timestamp=datetime.datetime.now(datetime.timezone.utc),
            )
            await transcript_channel.send(embed=summary, file=transcript_file)

        self.store.delete(channel.id)
        await channel.delete(reason=f"Ticket supprimé par {interaction.user}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
