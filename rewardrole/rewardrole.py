import discord
from redbot.core import commands, Config
from datetime import timedelta, datetime, timezone
import asyncio
import re

class RewardRole(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1995987654321, force_registration=True)
        default_guild = {
            "roles": {},
            "log_channel": None
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
                        try:
                            if role in member.roles and not any(excluded_role in member.roles for excluded_role in excluded_roles):
                                min_messages = role_data["min_messages"]
                                timeframe = timedelta(days=role_data["timeframe_days"])
                                user_message_count = 0
                                count_only_link_messages = role_data.get("count_only_link_messages", False)
                                for channel in guild.channels:
                                    # Check if member has the permissions to send messages in the channel
                                    permissions = channel.permissions_for(member)
                                    if not permissions.send_messages:
                                        continue
                                    overwrites = channel.overwrites_for(role)
                                    if overwrites.send_messages is False:
                                        continue
                                    if channel.category_id in role_data.get("ignored_categories", []):
                                        continue
                                    if isinstance(channel, discord.TextChannel) or isinstance(channel, discord.Thread):
                                        if channel.id in role_data.get("ignored_channels", []):
                                            continue
                                        # await self.log(guild, f'Checking messages in channel {channel.name}')  # Debug Log
                                        user_message_count += await self.process_channel_or_thread(channel, member, timeframe, count_only_link_messages, guild)
                                    if isinstance(channel, discord.ForumChannel):
                                        if channel.id in role_data.get("ignored_channels", []):
                                            continue
                                        for thread in channel.threads:
                                            # await self.log(guild, f'Checking messages in thread {thread.name}')  # Debug Log
                                            user_message_count += await self.process_channel_or_thread(thread, member, timeframe, count_only_link_messages, guild)

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
            await asyncio.sleep(4 * 60 * 60)  # Run the task every 4 hours

    async def process_channel_or_thread(self, channel_or_thread, member, timeframe, count_only_link_messages, guild):
        message_count = 0
        now = datetime.now(timezone.utc)
        earliest_time = now - timeframe
        async for message in channel_or_thread.history(limit=None, after=earliest_time):
            if message.author == member:
                if count_only_link_messages:
                    urls = re.findall('http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', message.content)
                    non_link_content = re.sub('http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', message.content).strip()
                    if not urls or non_link_content:
                        message_count += 1
                else:
                    message_count += 1
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
    async def add_role_condition(self, ctx, role: discord.Role, min_messages: int, timeframe_days: int, reward_role: discord.Role, count_only_link_messages: bool, excluded_roles: commands.Greedy[discord.Role], ignored_channels: commands.Greedy[discord.TextChannel]=None, ignored_categories: commands.Greedy[discord.CategoryChannel]=None):
        """Add a role condition for a specific role."""

        async with self.config.guild(ctx.guild).roles() as roles:
            roles[str(role.id)] = {
                "min_messages": min_messages,
                "timeframe_days": timeframe_days,
                "reward_role": reward_role.id,
                "count_only_link_messages": count_only_link_messages,
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

        pages = []
        for role_id, role_data in roles_data.items():
            role = ctx.guild.get_role(int(role_id))
            reward_role = ctx.guild.get_role(role_data["reward_role"])
            excluded_roles = [ctx.guild.get_role(excluded_role_id) for excluded_role_id in role_data["excluded_roles"]]
            ignored_channels = [ctx.guild.get_channel(channel_id) for channel_id in role_data["ignored_channels"]]
            ignored_categories = [ctx.guild.get_channel(category_id) for category_id in role_data["ignored_categories"]]
            count_only_link_messages = role_data.get("count_only_link_messages", False)

            # Create an embed for each role
            default_color = await ctx.embed_color()
            embed = discord.Embed(title=f"{role.name}", color=default_color)
            embed.add_field(
                name="Details",
                value=(
                    f"**Min messages:** {role_data['min_messages']}\n"
                    f"**Timeframe:** {role_data['timeframe_days']} days\n"
                    f"**Reward role:** {reward_role.mention}\n"
                    f"**Count messages that only contain links:** {'Yes' if count_only_link_messages else 'No'}\n"
                    f"**Excluded roles:** {', '.join([r.mention for r in excluded_roles if r])}\n"
                    f"**Ignored channels:** {', '.join([ch.mention for ch in ignored_channels if ch])}\n"
                    f"**Ignored categories:** {', '.join([cat.name for cat in ignored_categories if cat])}"
                ),
                inline=False
            )
            pages.append(embed)

        await self.paginate_roles(ctx, pages)

    @rewardrole.command(name="setlog")
    async def set_log_channel(self, ctx, channel: discord.TextChannel, enable: bool):
        """
        Set the log channel for the guild. Use 'true' to enable logging to the specified channel, 'false' to disable.
        """
        if enable:
            await self.config.guild(ctx.guild).log_channel.set(channel.id)
            await ctx.send(f"Log channel set to {channel.mention} and logging enabled.")
        else:
            await self.config.guild(ctx.guild).log_channel.set(None)
            await ctx.send("Logging has been disabled.")

    async def paginate_roles(self, ctx, pages):
        current_page = 0
        message = await ctx.send(embed=pages[current_page])

        # Adding reactions for navigation
        await message.add_reaction("⬅️")
        await message.add_reaction("➡️")

        def check(reaction, user):
            return user == ctx.author and reaction.message.id == message.id and str(reaction.emoji) in ["⬅️", "➡️"]

        while True:
            try:
                reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)

                if str(reaction.emoji) == "➡️" and current_page < len(pages) - 1:
                    current_page += 1
                    await message.edit(embed=pages[current_page])
                    await message.remove_reaction(reaction, user)

                elif str(reaction.emoji) == "⬅️" and current_page > 0:
                    current_page -= 1
                    await message.edit(embed=pages[current_page])
                    await message.remove_reaction(reaction, user)

                else:
                    await message.remove_reaction(reaction, user)

            except asyncio.TimeoutError:
                await message.clear_reactions()
                break
