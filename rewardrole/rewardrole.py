import discord
import re
from redbot.core import commands, Config
from datetime import timedelta
import asyncio

class RewardRole(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1995987654321)
        default_guild = {
            "roles": {}
        }
        self.config.register_guild(**default_guild)
        self.bg_task = self.bot.loop.create_task(self.update_roles())

    async def update_roles(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            for guild in self.bot.guilds:
                roles = await self.config.guild(guild).roles()
                for role_id, role_data in roles.items():
                    role = guild.get_role(int(role_id))
                    reward_role = guild.get_role(role_data["reward_role"])
                    excluded_roles = [guild.get_role(excluded_role_id) for excluded_role_id in role_data["excluded_roles"]]
                    for member in guild.members:
                        if role in member.roles and not any(excluded_role in member.roles for excluded_role in excluded_roles):
                            min_messages = role_data["min_messages"]
                            timeframe = timedelta(days=role_data["timeframe_days"])
                            after = member.joined_at - timeframe
                            message_count = 0

                            for channel in guild.text_channels:
                                if channel.id in role_data["ignored_channels"]:
                                    continue

                                messages = await channel.history(limit=100, after=after).flatten()
                                user_messages = [msg for msg in messages if msg.author == member]

                                message_count += len(user_messages)

                            if message_count >= min_messages:
                                if reward_role not in member.roles:
                                    await member.add_roles(reward_role)
                            else:
                                if reward_role in member.roles:
                                    await member.remove_roles(reward_role)

            await asyncio.sleep(4 * 60 * 60) # Run the task every 4 hours

    @commands.group()
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def rewardrole(self, ctx):
        """Commands for configuring RewardRole"""
        pass

    @rewardrole.command(name="add")
    async def add_role_condition(self, ctx, role: discord.Role, min_messages: int, timeframe_days: int, reward_role: discord.Role, excluded_roles: commands.Greedy[discord.Role], ignored_channels: commands.Greedy[discord.TextChannel]=None):
        """Add a role condition for a specific role."""

        async with self.config.guild(ctx.guild).roles() as roles:
            roles[str(role.id)] = {
                "min_messages": min_messages,
                "timeframe_days": timeframe_days,
                "reward_role": reward_role.id,
                "excluded_roles": [excluded_role.id for excluded_role in excluded_roles],
                "ignored_channels": [channel.id for channel in ignored_channels]
            }

        await ctx.send(f"Role condition for {role.name} added successfully.")

    @rewardrole.command(name="remove")
    async def remove_role_condition(self, ctx, role: discord.Role):
        """Remove a role condition for a specific role."""

        async with self.config.guild(ctx.guild).roles() as roles:
            if str(role.id) in roles:
                del roles[str(role.id)]
                await ctx.send(f"Role condition for {role.name} removed successfully.")
            else:
                await ctx.send(f"No role condition found for {role.name}.")

    @rewardrole.command(name="list")
    async def list_role_conditions(self, ctx):
        """List the configured role conditions."""
        roles_data = await self.config.guild(ctx.guild).roles()
        if not roles_data:
            await ctx.send("No role conditions have been configured.")
            return

        conditions = []
        for role_id, role_data in roles_data.items():
            role = ctx.guild.get_role(int(role_id))
            reward_role = ctx.guild.get_role(role_data["reward_role"])
            excluded_roles = [ctx.guild.get_role(excluded_role_id) for excluded_role_id in role_data["excluded_roles"]]
            ignored_channels = [ctx.guild.get_channel(channel_id) for channel_id in role_data["ignored_channels"]]
            conditions.append(f"Role: {role.name} | Min Messages: {role_data['min_messages']} | Timeframe (days): {role_data['timeframe_days']} | Reward Role: {reward_role.name} | Excluded Roles: {', '.join(excluded_role.name for excluded_role in excluded_roles)} | Ignored Channels: {', '.join(channel.name for channel in ignored_channels)}")

        await ctx.send("\n".join(conditions))
        
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        if not message.guild:
            return

        roles = await self.config.guild(message.guild).roles()

        for role_id, role_data in roles.items():
            role = message.guild.get_role(int(role_id))
            excluded_roles = [message.guild.get_role(excluded_role_id) for excluded_role_id in role_data["excluded_roles"]]
            if role in message.author.roles and not any(excluded_role in message.author.roles for excluded_role in excluded_roles):
                if message.channel.id in role_data["ignored_channels"]:
                    return

                link_only_regex = r'^\s*<?(?:http|https|ftp)://\S+\b\/*?>?\s*$'
                if re.match(link_only_regex, message.content):
                    return

                # Check messages in the specified timeframe and count them
                min_messages = role_data["min_messages"]
                timeframe = timedelta(days=role_data["timeframe_days"])
                after = message.created_at - timeframe

                messages = [msg async for msg in message.channel.history(limit=100, after=after)]
                user_messages = [msg for msg in messages if msg.author == message.author]

                if len(user_messages) >= min_messages:
                    reward_role = message.guild.get_role(role_data["reward_role"])
                    if reward_role not in message.author.roles:
                        await message.author.add_roles(reward_role)
                else:
                    reward_role = message.guild.get_role(role_data["reward_role"])
                    if reward_role in message.author.roles:
                        await message.author.remove_roles(reward_role)
