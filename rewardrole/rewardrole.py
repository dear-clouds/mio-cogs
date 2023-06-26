import discord
from redbot.core import commands, Config
from datetime import timedelta, datetime, timezone
import asyncio

class RewardRole(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1995987654321, force_registration=True)
        default_guild = {
            "roles": {},
            "last_message_ids": {},
            "log_channel": None
        }
        self.config.register_guild(**default_guild)
        self.bg_task = self.bot.loop.create_task(self.update_roles())

    async def update_roles(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            for guild in self.bot.guilds:
                await self.log(guild, f'Checking guild {guild.name}')  # Debug Log
                roles = await self.config.guild(guild).roles()
                await self.log(guild, f'Found {len(roles)} role(s) in the configuration')  # Debug Log
                last_message_ids = await self.config.guild(guild).last_message_ids()
                for role_id, role_data in roles.items():
                    role = guild.get_role(int(role_id))
                    reward_role = guild.get_role(role_data["reward_role"])
                    excluded_roles = [guild.get_role(excluded_role_id) for excluded_role_id in role_data["excluded_roles"]]
                    await self.log(guild, f'Processing role {role.name}')  # Debug Log
                    for member in guild.members:
                        try:
                            if role in member.roles and not any(excluded_role in member.roles for excluded_role in excluded_roles):
                                await self.log(guild, f'Processing member {member.name}')  # Debug Log
                                min_messages = role_data["min_messages"]
                                timeframe = timedelta(days=role_data["timeframe_days"])
                                user_message_count = 0
                                for channel in guild.channels:
                                    # Check if member has the permissions to send messages in the channel
                                    permissions = channel.permissions_for(member)
                                    if not permissions.send_messages:
                                        continue
                                    overwrites = channel.overwrites_for(role)
                                    if overwrites.send_messages is False:
                                        continue
                                    if isinstance(channel, discord.CategoryChannel) and channel.id in role_data.get("ignored_categories", []):
                                        continue
                                    if isinstance(channel, discord.TextChannel) or isinstance(channel, discord.Thread):
                                        if channel.id in role_data.get("ignored_channels", []):
                                            continue
                                        await self.log(guild, f'Checking messages in channel {channel.name}')  # Debug Log
                                        user_message_count += await self.process_channel_or_thread(channel, member, timeframe, last_message_ids, guild)
                                    if isinstance(channel, discord.ForumChannel):
                                        for thread in channel.threads:
                                            await self.log(guild, f'Checking messages in thread {thread.name}')  # Debug Log
                                            user_message_count += await self.process_channel_or_thread(thread, member, timeframe, last_message_ids, guild)

                                await self.log(guild, f'Finished processing member {member.name}. Message count: {user_message_count}')  # Debug Log
                                if user_message_count >= min_messages:
                                    if reward_role not in member.roles:
                                        await self.log(guild, f'Adding reward role to {member.name}')  # Debug Log
                                        await member.add_roles(reward_role)
                                else:
                                    if reward_role in member.roles:
                                        await self.log(guild, f'Removing reward role from {member.name}')  # Debug Log
                                        await member.remove_roles(reward_role)
                        except Exception as e:
                            await self.log(guild, f'An error occurred while processing member {member.name}: {str(e)}')  # Error Log
                            continue  # Continue with the next member even if an error occurred
                await self.config.guild(guild).last_message_ids.set(last_message_ids)
            await asyncio.sleep(4 * 60 * 60)  # Run the task every 4 hours

    async def process_channel_or_thread(self, channel_or_thread, member, timeframe, last_message_ids, guild):
        message_count = 0
        now = datetime.now(timezone.utc)
        earliest_time = now - timeframe
        last_message_id = last_message_ids.get(str(channel_or_thread.id))
        if last_message_id:
            after = discord.Object(id=int(last_message_id))
        else:
            after = earliest_time
        async for message in channel_or_thread.history(limit=None, after=after):
            if message.author == member and message.created_at > earliest_time:
                message_count += 1
                if str(channel_or_thread.id) not in last_message_ids or message.id > int(last_message_ids[str(channel_or_thread.id)]):
                    last_message_ids[str(channel_or_thread.id)] = str(message.id)
        return message_count
            
    async def log(self, guild, message):
        log_channel_id = await self.config.guild(guild).log_channel()
        if log_channel_id:
            log_channel = guild.get_channel(log_channel_id)
            if log_channel:
                await log_channel.send(message)

    @commands.group()
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def rewardrole(self, ctx):
        """Commands for configuring RewardRole"""
        pass

    @rewardrole.command(name="add")
    async def add_role_condition(self, ctx, role: discord.Role, min_messages: int, timeframe_days: int, reward_role: discord.Role, excluded_roles: commands.Greedy[discord.Role], ignored_channels: commands.Greedy[discord.TextChannel]=None, ignored_categories: commands.Greedy[discord.CategoryChannel]=None):
        """Add a role condition for a specific role."""

        async with self.config.guild(ctx.guild).roles() as roles:
            roles[str(role.id)] = {
                "min_messages": min_messages,
                "timeframe_days": timeframe_days,
                "reward_role": reward_role.id,
                "excluded_roles": [excluded_role.id for excluded_role in excluded_roles],
                "ignored_channels": [channel.id for channel in ignored_channels],
                "ignored_categories": [category.id for category in ignored_categories]
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

        embed = discord.Embed()
        for role_id, role_data in roles_data.items():
            role = ctx.guild.get_role(int(role_id))
            reward_role = ctx.guild.get_role(role_data["reward_role"])
            excluded_roles = [ctx.guild.get_role(excluded_role_id) for excluded_role_id in role_data["excluded_roles"]]
            ignored_channels = [ctx.guild.get_channel(channel_id) for channel_id in role_data["ignored_channels"]]
            ignored_categories = [ctx.guild.get_channel(category_id) for category_id in role_data.get("ignored_categories", [])]

            field_value = (
                f"Min Messages: {role_data['min_messages']}\n"
                f"Timeframe (days): {role_data['timeframe_days']}\n"
                f"Reward Role: {reward_role.mention}\n"
                f"Excluded Roles: {', '.join(excluded_role.mention for excluded_role in excluded_roles if excluded_role)}\n"  # Ensure the role exists
                f"Ignored Channels: {', '.join(channel.mention for channel in ignored_channels if channel)}\n"  # Ensure the channel exists
                f"Ignored Categories: {', '.join(category.mention for category in ignored_categories if category)}"  # Ensure the category exists
            )
            embed.add_field(name=f"Role: {role.name}", value=field_value, inline=False)

        await ctx.send(embed=embed)
        
    @rewardrole.command(name="logs")
    async def logs(self, ctx, channel: discord.TextChannel):
        """Sets the logging channel for the guild."""
        await self.config.guild(ctx.guild).log_channel.set(channel.id)
        await ctx.send(f"Logging channel has been set to: {channel.mention}")
    
