from typing import Optional
import discord
from discord import app_commands
from discord.app_commands import check
from datetime import datetime, timedelta
import aiohttp
from discord import Embed
from discord.ui import View, Button
from discord.ui import View, Button, Modal, TextInput
from discord.utils import get


# Set your guild ID here
MY_GUILD = discord.Object(id=1399429382766071808)

FULL_ACCESS_ROLE_ID = 1400554337905934427
LIMITED_ACCESS_ROLE_ID = 1400554329533841519
LOG_CHANNEL_ID = 1400554971572732087
VERIFY_CHANNEL_ID = 1400409821290692739
VERIFY_ROLE_ID = 1399493722491584612
BOOST_CHANNEL_ID = 1400550755336716328  
snipe_cache = {}  # {channel_id: (author, content, timestamp)}
user_vcs = {}
LOBBY_VC_ID = 1400558994405331034  # Join VC ID
VC_PANEL_CHANNEL_ID = 1399438389513683135
DEFAULT_VC_LIMIT = 5

# Name template for new VCs
def vc_name_for(user: discord.Member) -> str:
    return f"{user.display_name}'s VC"

class VCPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(RenameVCButton())
        self.add_item(ChangeLimitButton())
        self.add_item(LockUnlockButton())


class RenameVCButton(Button):
    def __init__(self):
        super().__init__(label="Rename VC", style=discord.ButtonStyle.primary, custom_id="rename_vc")

    async def callback(self, interaction: discord.Interaction):
        vc = interaction.user.voice.channel if interaction.user.voice else None
        if not vc or vc.id != user_vcs.get(interaction.user.id):
            return await interaction.response.send_message("❌ You must be in your own VC to rename it.", ephemeral=True)

        await interaction.response.send_modal(RenameVCModal(vc.id))


class RenameVCModal(discord.ui.Modal, title="Rename your VC"):
    name = discord.ui.TextInput(label="New VC Name", max_length=100)

    def __init__(self, channel_id: int):
        super().__init__()
        self.channel_id = channel_id

    async def on_submit(self, interaction: discord.Interaction):
        vc = interaction.guild.get_channel(self.channel_id)
        if vc:
            await vc.edit(name=self.name.value)
            await interaction.response.send_message(f"✅ Renamed VC to `{self.name.value}`", ephemeral=True)
        else:
            await interaction.response.send_message("❌ VC not found.", ephemeral=True)


class ChangeLimitButton(Button):
    def __init__(self):
        super().__init__(label="Change Limit", style=discord.ButtonStyle.primary, custom_id="change_limit")

    async def callback(self, interaction: discord.Interaction):
        vc = interaction.user.voice.channel if interaction.user.voice else None
        if not vc or vc.id != user_vcs.get(interaction.user.id):
            return await interaction.response.send_message("❌ You must be in your own VC to change its limit.", ephemeral=True)

        await interaction.response.send_modal(ChangeLimitModal(vc.id))


class ChangeLimitModal(discord.ui.Modal, title="Set VC User Limit"):
    limit = discord.ui.TextInput(label="New User Limit", placeholder="Enter a number between 1 and 99", max_length=2)

    def __init__(self, channel_id: int):
        super().__init__()
        self.channel_id = channel_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            new_limit = int(self.limit.value)
            if not (1 <= new_limit <= 99):
                raise ValueError()
        except ValueError:
            return await interaction.response.send_message("❌ Please enter a valid number between 1 and 99.", ephemeral=True)

        vc = interaction.guild.get_channel(self.channel_id)
        if vc:
            await vc.edit(user_limit=new_limit)
            await interaction.response.send_message(f"✅ VC user limit set to `{new_limit}`", ephemeral=True)
        else:
            await interaction.response.send_message("❌ VC not found.", ephemeral=True)


class LockUnlockButton(Button):
    def __init__(self):
        super().__init__(label="Lock/Unlock VC", style=discord.ButtonStyle.secondary, custom_id="lock_unlock")

    async def callback(self, interaction: discord.Interaction):
        vc = interaction.user.voice.channel if interaction.user.voice else None
        if not vc or vc.id != user_vcs.get(interaction.user.id):
            return await interaction.response.send_message("❌ You must be in your own VC to lock/unlock it.", ephemeral=True)

        everyone = interaction.guild.default_role
        perms = vc.overwrites_for(everyone)

        # Toggle connect permission
        locked = perms.connect is False
        perms.connect = None if locked else False
        await vc.set_permissions(everyone, overwrite=perms)

        status = "🔓 Unlocked" if locked else "🔒 Locked"
        await interaction.response.send_message(f"{status} your VC.", ephemeral=True)


async def log_action(action: str, moderator: discord.User, target: discord.User, reason: str):
    log_channel = client.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        embed = discord.Embed(
            description=(
                f"**Action:** {action}\n"
                f"**User:** {target.mention} (`{target.id}`)\n"
                f"**By:** {moderator.mention} (`{moderator.id}`)\n"
                f"**Reason:** {reason}"
            )
        )
        embed.set_footer(text=f"Made by zayne :p - {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")
        await log_channel.send(embed=embed)


def has_full_access():
    return check(lambda i: any(role.id == FULL_ACCESS_ROLE_ID for role in i.user.roles))

def has_limited_access():
    return check(lambda i: any(role.id in [FULL_ACCESS_ROLE_ID, LIMITED_ACCESS_ROLE_ID] for role in i.user.roles))

class MyClient(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        self.tree.copy_global_to(guild=MY_GUILD)
        await self.tree.sync(guild=MY_GUILD)


intents = discord.Intents.default()
intents.members = True
intents.message_content = True  # ✅ Required for on_message to see normal messages
client = MyClient(intents=intents)

@client.event
async def on_member_update(before: discord.Member, after: discord.Member):
    # Ignore if already boosted
    if before.premium_since is None and after.premium_since is not None:
        boost_channel = after.guild.get_channel(BOOST_CHANNEL_ID)
        if boost_channel:
            await boost_channel.send(
                f"🎉 {after.mention} just **boosted** the server! Thank you so much 💖"
            )

@client.event
@client.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    # The category ID where personal VCs should be created
    personal_vc_category_id = 1399436406010548366

    # Check if user joined the lobby VC
    if after.channel and after.channel.id == LOBBY_VC_ID:
        if member.id not in user_vcs:
            guild = member.guild
            category = guild.get_channel(personal_vc_category_id)
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(connect=False),
                member: discord.PermissionOverwrite(connect=True, manage_channels=True, mute_members=True, deafen_members=True)
            }
            new_vc = await guild.create_voice_channel(
                name=vc_name_for(member),
                overwrites=overwrites,
                user_limit=DEFAULT_VC_LIMIT,
                category=category,
                reason="Created personal VC for user from lobby join"
            )
            user_vcs[member.id] = new_vc.id
            await member.move_to(new_vc)

    # Handle leaving a VC
    if before.channel:
        # Check if it was a personal VC we manage
        if member.id in user_vcs and user_vcs[member.id] == before.channel.id:
            channel = before.channel
            if len(channel.members) == 0:
                await channel.delete(reason="Deleting empty personal VC")
                user_vcs.pop(member.id, None)

                
@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # Only act in the verify channel
    if message.channel.id == VERIFY_CHANNEL_ID:
        # If it's not a system interaction (e.g., /verify), delete it
        if not message.interaction:
            try:
                await message.delete()
            except discord.Forbidden:
                pass

@client.event
async def on_message_delete(message: discord.Message):
    if message.author.bot or not message.content:
        return

    snipe_cache[message.channel.id] = (
        message.author,
        message.content,
        message.created_at
    )


@client.event
async def on_ready():
    await client.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="over you"))
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    print('------')

# Store previous invite state
invite_cache = {}

@client.event
async def on_ready():
    await client.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="over you"))
    print(f'Logged in as {client.user} (ID: {client.user.id})')

    for guild in client.guilds:
        invites = await guild.invites()
        invite_cache[guild.id] = {invite.code: invite.uses for invite in invites}

    print('Invite cache populated.')
    print('------')



@client.event
async def on_member_join(member: discord.Member):
    if member.guild.id != 1399429382766071808:
        return

    # --- Welcome message ---
    welcome_channel = member.guild.get_channel(1400205804090429580)
    if welcome_channel:
        welcome_message = (
            f"Welcome, {member.mention} to Enqil! Make sure to have a look at:\n"
            f"https://discord.com/channels/1399429382766071808/1399433735753171155\n"
            f"https://discord.com/channels/1399429382766071808/1399435043490889799\n"
            f"Enjoy your stay!"
        )
        await welcome_channel.send(welcome_message)

    # --- Invite tracking ---
    log_channel = member.guild.get_channel(1400406869180289107)
    if not log_channel:
        return

    # Fetch current invites
    current_invites = await member.guild.invites()
    old_invites = invite_cache.get(member.guild.id, {})

    used_invite = None
    for invite in current_invites:
        old_uses = old_invites.get(invite.code, 0)
        if invite.uses > old_uses:
            used_invite = invite
            break

    # Update cache
    invite_cache[member.guild.id] = {invite.code: invite.uses for invite in current_invites}

    # Create embed message
    if used_invite and used_invite.inviter:
        inviter = used_invite.inviter
        total_invites = sum(i.uses for i in current_invites if i.inviter == inviter)

        embed = discord.Embed(
            description=(
                f"{member.mention} was invited by {inviter.mention} via `{used_invite.code}`.\n"
                f"{inviter.mention} now has **{total_invites}** total invite(s)."
            )
        )
        embed.set_footer(text=f"Made by zayne :p - {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")
        await log_channel.send(embed=embed)
    else:
        embed = discord.Embed(description=f"{member.mention} joined, but the inviter could not be determined.")
        embed.set_footer(text=f"Made by zayne :p - {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")
        await log_channel.send(embed=embed)



def create_embed(description: str) -> discord.Embed:
    embed = discord.Embed(description=description)  # No color
    embed.set_footer(text=f"Made by zayne :p - {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")
    return embed


@client.tree.command(name="ban")
@has_full_access()
@app_commands.describe(user="User to ban", reason="Reason for ban")
async def ban(interaction: discord.Interaction, user: discord.Member, reason: Optional[str] = "No reason provided"):
    try:
        await user.send(f"You have been **banned** from Enqil.\nReason: {reason}")
    except discord.Forbidden:
        pass

    await user.ban(reason=reason)
    await interaction.response.send_message(f"{interaction.user.mention} has **banned** {user.mention}.")
    await log_action("banned", interaction.user, user, reason)


@client.tree.command(name="kick")
@has_limited_access()
@app_commands.describe(user="User to kick", reason="Reason for kick")
async def kick(interaction: discord.Interaction, user: discord.Member, reason: Optional[str] = "No reason provided"):
    try:
        await user.send(f"You have been **kicked** from Enqil.\nReason: {reason}")
    except discord.Forbidden:
        pass

    await user.kick(reason=reason)
    await interaction.response.send_message(f"{interaction.user.mention} has **kicked** {user.mention}.")
    await log_action("kicked", interaction.user, user, reason)


@client.tree.command(name="timeout")
@has_limited_access()
@app_commands.describe(user="User to timeout", duration="Duration in minutes", reason="Reason for timeout")
async def timeout(interaction: discord.Interaction, user: discord.Member, duration: int, reason: Optional[str] = "No reason provided"):
    try:
        await user.send(f"You have been **timed out** from Enqil for {duration} minutes.\nReason: {reason}")
    except discord.Forbidden:
        pass

    await user.timeout(timedelta(minutes=duration), reason=reason)
    await interaction.response.send_message(f"{interaction.user.mention} has **timed out** {user.mention} for {duration} minute(s).")
    await log_action(f"timed out ({duration}m)", interaction.user, user, reason)

@client.tree.command(name="verify")
async def verify(interaction: discord.Interaction):
    """Assigns the verify role to the user."""
    if interaction.channel.id != VERIFY_CHANNEL_ID:
        await interaction.response.send_message("You can only use this command in the verify channel.", ephemeral=True)
        return

    role = interaction.guild.get_role(VERIFY_ROLE_ID)
    if not role:
        await interaction.response.send_message("Verify role not found.", ephemeral=True)
        return

    if role in interaction.user.roles:
        await interaction.response.send_message("You are already verified!", ephemeral=True)
        return

    await interaction.user.add_roles(role)
    await interaction.response.send_message(f"✅ You’ve been verified and given the {role.name} role!", ephemeral=True)

@client.tree.command(name="snipe")
async def snipe(interaction: discord.Interaction):
    """Shows the last deleted message in this channel."""
    data = snipe_cache.get(interaction.channel.id)

    if not data:
        await interaction.response.send_message("There's nothing to snipe 🫣")
        return

    author, content, timestamp = data

    embed = discord.Embed(
        description=content,
        timestamp=timestamp
    )
    embed.set_author(name=f"{author}", icon_url=author.display_avatar.url)
    embed.set_footer(text=f"Made by zayne :p - {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")
    await interaction.response.send_message(embed=embed)



@client.tree.command(name="lookup")
@app_commands.describe(username="Roblox username to lookup")
async def lookup(interaction: discord.Interaction, username: str):
    await interaction.response.defer()
    async with aiohttp.ClientSession() as session:
        # Get Roblox user ID
        async with session.post(
            "https://users.roproxy.com/v1/usernames/users",
            json={"usernames": [username], "excludeBannedUsers": False}
        ) as resp:
            data = await resp.json()
            if not data.get("data"):
                return await interaction.followup.send("❌ Roblox user not found.")
            user = data["data"][0]
            user_id = user["id"]

        # Get profile info
        async with session.get(f"https://users.roproxy.com/v1/users/{user_id}") as resp:
            profile = await resp.json()

        # Get Rolimon RAP info
        async with session.get(f"https://api.rolimons.com/player/{user_id}") as resp:
            if resp.status == 200:
                rolimon_data = await resp.json()
                rap = rolimon_data.get("rap", "Unavailable")
                value = rolimon_data.get("value", "Unavailable")
                rank = rolimon_data.get("rank", "Unavailable")
            else:
                rap = value = rank = "Unavailable"

        # Get avatar thumbnail
        async with session.get(
            f"https://thumbnails.roblox.com/v1/users/avatar?userIds={user_id}&size=420x420&format=Png&isCircular=false"
        ) as resp:
            avatar_data = await resp.json()
            avatar = avatar_data["data"][0]["imageUrl"]

    # Build embed
    embed = discord.Embed(
        title=f"{profile.get('displayName', username)}'s Roblox Profile",
        description=f"[Visit profile](https://www.roblox.com/users/{user_id}/profile)",
        color=discord.Color.default()
    )
    embed.set_thumbnail(url=avatar)
    embed.add_field(name="Username", value=profile.get("name", "Unknown"), inline=True)
    embed.add_field(name="User ID", value=user_id, inline=True)
    embed.add_field(name="Join Date", value=profile.get("created", "N/A")[:10], inline=True)
    embed.add_field(name="RAP", value=str(rap), inline=True)
    embed.add_field(name="Value", value=str(value), inline=True)
    embed.add_field(name="Rank", value=str(rank), inline=True)
    embed.add_field(name="Bio", value=profile.get("description") or "No bio", inline=False)
    embed.set_footer(text=f"Made by zayne :p - {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")

    await interaction.followup.send(embed=embed)

@client.tree.command(name="purge")
@app_commands.describe(amount="Number of messages to delete (max 100)")
async def purge(interaction: discord.Interaction, amount: int):
    # Roles allowed to use purge
    allowed_roles = {1400554337905934427, 1400554329533841519}  # admin + mod role IDs

    # Check permissions
    member = interaction.user
    if not (
        member.guild_permissions.administrator
        or any(role.id in allowed_roles for role in member.roles)
    ):
        await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
        return

    if amount < 1 or amount > 100:
        await interaction.response.send_message("❌ Please specify an amount between 1 and 100.", ephemeral=True)
        return

    await interaction.response.defer()

    deleted = await interaction.channel.purge(limit=amount)

    await interaction.followup.send(f"✅ Deleted {len(deleted)} messages.", ephemeral=True)

    # Log to your mod log channel
    log_channel = interaction.guild.get_channel(1400554971572732087)
    if log_channel:
        embed = discord.Embed(
            title="Messages Purged",
            description=f"{member.mention} purged {len(deleted)} messages in {interaction.channel.mention}.",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text=f"Made by zayne :p - {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")
        await log_channel.send(embed=embed)

@client.tree.command(name="raids")
@app_commands.describe(link="Link to the raid event or info")
async def raids(interaction: discord.Interaction, link: str):
    member = interaction.user
    if not member.guild_permissions.administrator:
        await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
        return

    # Send @everyone message and delete it immediately (ghost ping)
    ping_msg = await interaction.channel.send("@everyone")
    await ping_msg.delete()

    embed = discord.Embed(
        title="Raid Announcement",
        description=f"{member.mention} has started a raid!",
        color=discord.Color.default(),  # no color
        timestamp=discord.utils.utcnow()
    )
    embed.add_field(name="Link", value=link, inline=False)
    embed.set_footer(text=f"Made by zayne :p - {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")

    # Respond with embed (no @everyone content here to avoid double ping)
    await interaction.response.send_message(embed=embed)

@client.tree.command(name="untimeout")
@app_commands.describe(member="The member to remove timeout from")
async def untimeout(interaction: discord.Interaction, member: discord.Member):
    allowed_roles = {1400554337905934427, 1400554329533841519}
    author = interaction.user

    if not (author.guild_permissions.administrator or any(role.id in allowed_roles for role in author.roles)):
        await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
        return

    if member.timed_out_until is None:
        await interaction.response.send_message(f"❌ {member.mention} is not currently timed out.", ephemeral=True)
        return

    await member.edit(timed_out_until=None)
    await interaction.response.send_message(f"✅ {member.mention} has been un-timed out.")

    try:
        await member.send(f"You have been un-timed out in **{interaction.guild.name}** by {author}.")
    except:
        # User has DMs closed
        pass

    log_channel = interaction.guild.get_channel(1400554971572732087)
    if log_channel:
        embed = discord.Embed(
            title="Member Untimeout",
            description=f"{author.mention} removed timeout from {member.mention}.",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_footer(text=f"Made by zayne :p - {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")
        await log_channel.send(embed=embed)

@client.tree.command(name="vcpanel")
async def vcpanel(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Only administrators can use this command.", ephemeral=True)

    embed = discord.Embed(
        title="VC Panel",
        description="Use the buttons to control your VC.\nAvailable options:\n- Rename\n- Change user limit\n- Lock/Unlock\n- Kick users",
        color=discord.Color.default()
    )
    await interaction.channel.send(embed=embed, view=VCPanelView())
    await interaction.response.send_message("✅ VC Panel deployed!", ephemeral=True)

class VCPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(RenameButton())
        self.add_item(SlotButton())
        self.add_item(LockUnlockButton())

class RenameButton(Button):
    def __init__(self):
        super().__init__(label="Rename", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        user_vc_id = user_vcs.get(interaction.user.id)
        if not user_vc_id:
            return await interaction.response.send_message("❌ You don’t own a VC right now.", ephemeral=True)

        async def modal_callback(modal_interaction: discord.Interaction):
            new_name = modal_interaction.data["components"][0]["components"][0]["value"]
            channel = interaction.guild.get_channel(user_vc_id)
            if channel:
                await channel.edit(name=new_name)
                await modal_interaction.response.send_message(f"✅ Renamed VC to `{new_name}`", ephemeral=True)

        class RenameModal(discord.ui.Modal, title="Rename VC"):
            new_name = discord.ui.TextInput(label="New VC Name", max_length=100)

            async def on_submit(self, modal_interaction: discord.Interaction):
                await modal_callback(modal_interaction)

        await interaction.response.send_modal(RenameModal())

class SlotButton(Button):
    def __init__(self):
        super().__init__(label="Change Slots", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        user_vc_id = user_vcs.get(interaction.user.id)
        if not user_vc_id:
            return await interaction.response.send_message("❌ You don’t own a VC right now.", ephemeral=True)

        async def modal_callback(modal_interaction: discord.Interaction):
            value = modal_interaction.data["components"][0]["components"][0]["value"]
            try:
                limit = int(value)
                if not (1 <= limit <= 99):
                    raise ValueError
            except ValueError:
                return await modal_interaction.response.send_message("❌ Please enter a valid number (1–99).", ephemeral=True)

            vc = interaction.guild.get_channel(user_vc_id)
            if vc:
                await vc.edit(user_limit=limit)
                await modal_interaction.response.send_message(f"✅ VC slot limit set to {limit}", ephemeral=True)

        class SlotModal(discord.ui.Modal, title="Set VC Slots"):
            slots = discord.ui.TextInput(label="Max VC Users", placeholder="Enter a number between 1 and 99", max_length=2)

            async def on_submit(self, modal_interaction: discord.Interaction):
                await modal_callback(modal_interaction)

        await interaction.response.send_modal(SlotModal())

class LockUnlockButton(Button):
    def __init__(self):
        super().__init__(label="Lock/Unlock VC", style=discord.ButtonStyle.secondary, custom_id="lock_unlock")

    async def callback(self, interaction: discord.Interaction):
        vc = interaction.user.voice.channel if interaction.user.voice else None
        if not vc or vc.id != user_vcs.get(interaction.user.id):
            return await interaction.response.send_message("❌ You must be in your own VC to lock/unlock it.", ephemeral=True)

        everyone = interaction.guild.default_role
        perms = vc.overwrites_for(everyone)

        # Check if currently locked (connect explicitly denied)
        is_locked = perms.connect is False

        if is_locked:
            # Unlock: remove the explicit deny so members can connect
            perms.connect = None
            action = "🔓 Unlocked"
        else:
            # Lock: explicitly deny connect permission
            perms.connect = False
            action = "🔒 Locked"

        await vc.set_permissions(everyone, overwrite=perms)
        await interaction.response.send_message(f"{action} your VC.", ephemeral=True)

from discord.utils import get

# Role IDs (your provided ones)
AGE_ROLES = {
    "1️⃣": 1400209569170587651,  # 14+
    "2️⃣": 1400209566192631889,  # 16+
    "3️⃣": 1400209526002552902,  # 18+
}

GENDER_ROLES = {
    "1️⃣": 1400209718495940619,  # Girl
    "2️⃣": 1400209720849072238,  # Boy
}

PING_ROLES = {
    "1️⃣": 1400209833256288480,  # raid pings
    "2️⃣": 1400209836901142538,  # giveaway pings
    "3️⃣": 1400209843503239217,  # gamenight pings
}

# Store message IDs of the role messages so we know which reacts to listen to
selfrole_message_ids = set()

@client.tree.command(name="selfroles")
async def selfroles(interaction: discord.Interaction):
    """Sends self-role embeds for age, gender, and pings."""
    if interaction.guild.id != MY_GUILD.id:
        await interaction.response.send_message("This command can only be used in the main guild.", ephemeral=True)
        return

    # First embed: Age
    age_desc = (
        "React with the corresponding emoji to get the role:\n\n"
        "1️⃣ — 14+\n"
        "2️⃣ — 16+\n"
        "3️⃣ — 18+"
    )
    age_embed = discord.Embed(description=age_desc)
    age_embed.set_footer(text=f"Made by zayne :p - {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")

    # Second embed: Gender
    gender_desc = (
        "React with the corresponding emoji to get the role:\n\n"
        "1️⃣ — Girl\n"
        "2️⃣ — Boy"
    )
    gender_embed = discord.Embed(description=gender_desc)
    gender_embed.set_footer(text=f"Made by zayne :p - {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")

    # Third embed: Pings
    ping_desc = (
        "React with the corresponding emoji to get the role:\n\n"
        "1️⃣ — Raid pings\n"
        "2️⃣ — Giveaway pings\n"
        "3️⃣ — Game night pings"
    )
    ping_embed = discord.Embed(description=ping_desc)
    ping_embed.set_footer(text=f"Made by zayne :p - {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")

    # Send embeds separately and add reactions
    age_msg = await interaction.channel.send(embed=age_embed)
    gender_msg = await interaction.channel.send(embed=gender_embed)
    ping_msg = await interaction.channel.send(embed=ping_embed)

    # Add reactions to each message
    for emoji in ["1️⃣", "2️⃣", "3️⃣"]:
        await age_msg.add_reaction(emoji)
    for emoji in ["1️⃣", "2️⃣"]:
        await gender_msg.add_reaction(emoji)
    for emoji in ["1️⃣", "2️⃣", "3️⃣"]:
        await ping_msg.add_reaction(emoji)

    # Store message IDs to track reactions later
    selfrole_message_ids.update({age_msg.id, gender_msg.id, ping_msg.id})

    await interaction.response.send_message("Self-role messages sent!", ephemeral=True)


@client.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.message_id not in selfrole_message_ids:
        return  # Not a selfrole message

    guild = client.get_guild(payload.guild_id)
    if not guild:
        return

    member = guild.get_member(payload.user_id)
    if member is None or member.bot:
        return

    emoji = str(payload.emoji)

    # Figure out which message it is to know which role dict to use
    if payload.message_id in selfrole_message_ids:
        channel = guild.get_channel(payload.channel_id)
        if not channel:
            return
        # Fetch the message to verify
        try:
            message = await channel.fetch_message(payload.message_id)
        except:
            return

        # Determine role based on which message reacted to
        if payload.message_id == message.id:
            # Age message
            if message.embeds and "14+" in message.embeds[0].description:
                role_id = AGE_ROLES.get(emoji)
            # Gender message
            elif message.embeds and "Girl" in message.embeds[0].description:
                role_id = GENDER_ROLES.get(emoji)
            # Ping message
            elif message.embeds and "Raid pings" in message.embeds[0].description:
                role_id = PING_ROLES.get(emoji)
            else:
                role_id = None

            if role_id:
                role = guild.get_role(role_id)
                if role and role not in member.roles:
                    try:
                        await member.add_roles(role)
                    except discord.Forbidden:
                        pass


@client.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    if payload.message_id not in selfrole_message_ids:
        return  # Not a selfrole message

    guild = client.get_guild(payload.guild_id)
    if not guild:
        return

    member = guild.get_member(payload.user_id)
    if member is None or member.bot:
        return

    emoji = str(payload.emoji)

    # Same logic as add but remove roles
    channel = guild.get_channel(payload.channel_id)
    if not channel:
        return
    try:
        message = await channel.fetch_message(payload.message_id)
    except:
        return

    if payload.message_id == message.id:
        if message.embeds and "14+" in message.embeds[0].description:
            role_id = AGE_ROLES.get(emoji)
        elif message.embeds and "Girl" in message.embeds[0].description:
            role_id = GENDER_ROLES.get(emoji)
        elif message.embeds and "Raid pings" in message.embeds[0].description:
            role_id = PING_ROLES.get(emoji)
        else:
            role_id = None

        if role_id:
            role = guild.get_role(role_id)
            if role and role in member.roles:
                try:
                    await member.remove_roles(role)
                except discord.Forbidden:
                    pass


client.run(token)
