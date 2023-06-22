import discord
import re
from redbot.core import commands, Config
from datetime import timedelta, datetime
import asyncio

class RewardRole(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1995987654321, force_registration=True)
        default_guild = {
            "roles": {},
            "user_activity": {},
            "last_message_ids": {}
        }
        self.config.register_guild(**default_guild)
        self.bg_task = self.bot.loop.create_task(self.update_roles())

    async def update_roles(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            for guild in self.bot.guilds:
                roles = await self.config.guild(guild).roles()
                last_message_ids = await self.config.guild(guild).last_message_ids()
                for role_id, role_data in roles.items():
                    role = guild.get_role(int(role_id))
                    reward_role = guild.get_role(role_data["reward_role"])
                    excluded_roles = [guild.get_role(excluded_role_id) for excluded_role_id in role_data["excluded_roles"]]
                    for member in guild.members:
                        if role in member.roles and not any(excluded_role in member.roles for excluded_role in excluded_roles):
                            min_messages = role_data["min_messages"]
                            timeframe = timedelta(days=role_data["timeframe_days"])
                            user_message_count = 0
                            for channel in guild.text_channels:
                                if channel.id in role_data["ignored_channels"]:
                                    continue
                                try:
                                    last_message_id = last_message_ids.get(str(channel.id))
                                    if last_message_id:
                                        messages = channel.history(limit=100, after=discord.Object(id=last_message_id))
                                    else:
                                        messages = channel.history(limit=100)
                                    last_message = None
                                    async for message in messages:
                                        if message.author == member and message.created_at >= datetime.now() - timeframe:
                                            user_message_count += 1
                                        last_message = message
                                    if last_message:
                                        last_message_ids[str(channel.id)] = last_message.id
                                except discord.errors.Forbidden:
                                    continue  # Ignore channels the bot doesn't have access to
                            print(f'{member.name} message count: {user_message_count}')  # print user message count
                            if user_message_count >= min_messages:
                                if reward_role not in member.roles:
                                    print(f'Adding reward role to {member.name}')  # print user name when role is added
                                    await member.add_roles(reward_role)
                            else:
                                if reward_role in member.roles:
                                    print(f'Removing reward role from {member.name}')  # print user name when role is removed
                                    await member.remove_roles(reward_role)
                await self.config.guild(guild).last_message_ids.set(last_message_ids)
            await asyncio.sleep(1 * 60 * 60)  # Run the task every 1 hours

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

        embed = discord.Embed(color=discord.Color.blue())
        for role_id, role_data in roles_data.items():
            role = ctx.guild.get_role(int(role_id))
            reward_role = ctx.guild.get_role(role_data["reward_role"])
            excluded_roles = [ctx.guild.get_role(excluded_role_id) for excluded_role_id in role_data["excluded_roles"]]
            ignored_channels = [ctx.guild.get_channel(channel_id) for channel_id in role_data["ignored_channels"]]

            field_value = (
                f"Min Messages: {role_data['min_messages']}\n"
                f"Timeframe (days): {role_data['timeframe_days']}\n"
                f"Reward Role: {reward_role.mention}\n"
                f"Excluded Roles: {', '.join(excluded_role.mention for excluded_role in excluded_roles if excluded_role)}\n"  # Ensure the role exists
                f"Ignored Channels: {', '.join(channel.mention for channel in ignored_channels if channel)}"  # Ensure the channel exists
            )
            embed.add_field(name=f"Role: {role.name}", value=field_value, inline=False)

        await ctx.send(embed=embed)
        
    # @commands.Cog.listener()
    # async def on_message(self, message):
    #     if message.author.bot:
    #         return

    #     if not message.guild:
    #         return

    #     roles = await self.config.guild(message.guild).roles()
    #     user_activity = await self.config.guild(message.guild).user_activity()

    #     for role_id, role_data in roles.items():
    #         role = message.guild.get_role(int(role_id))
    #         excluded_roles = [message.guild.get_role(excluded_role_id) for excluded_role_id in role_data["excluded_roles"]]
    #         if role in message.author.roles and not any(excluded_role in message.author.roles for excluded_role in excluded_roles):
    #             if message.channel.id in role_data["ignored_channels"]:
    #                 return

    #             link_only_regex = r'^\s*<?(?:http|https|ftp)://\S+\b\/*?>?\s*$'
    #             if re.match(link_only_regex, message.content):
    #                 return

    #             user_activity_data = user_activity.get(str(message.author.id), {"messages": [], "last_message": message.created_at.timestamp()})

    #             user_activity_data['messages'].append(message.created_at.timestamp())

    #             timeframe = timedelta(days=role_data["timeframe_days"]).total_seconds()
    #             valid_timeframe = (datetime.now() - timedelta(seconds=timeframe)).timestamp()
    #             user_activity_data['messages'] = [msg_time for msg_time in user_activity_data['messages'] if msg_time >= valid_timeframe]

    #             user_activity_data['last_message'] = message.created_at.timestamp()
    #             user_activity[str(message.author.id)] = user_activity_data
    #             await self.config.guild(message.guild).user_activity.set(user_activity)
