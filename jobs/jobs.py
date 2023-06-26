import discord
from redbot.core import commands, Config, bank
from discord import Embed, Colour, Button, ButtonStyle
from typing import Optional

class Jobs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1995987654322)
        default_guild = {
            "job_channel_id": None,
            "roles": {},
            "jobs": {},
            "emoji": "\U0001F4BC"
        }
        self.config.register_guild(**default_guild)

    @commands.group()
    @commands.guild_only()
    async def jobs(self, ctx):
        """Manage jobs"""
        pass

    @jobs.command(name='channel')
    @commands.has_guild_permissions(administrator=True)
    async def set_channel(self, ctx, channel: discord.TextChannel):
        """Set the channel for jobs"""
        await self.config.guild(ctx.guild).job_channel_id.set(channel.id)
        await ctx.send(f"Job channel has been set to {channel.mention}")

    @jobs.command(name='emoji')
    @commands.has_guild_permissions(administrator=True)
    async def set_emoji(self, ctx, emoji: str):
        """Set the emoji for job reactions"""
        await self.config.guild(ctx.guild).emoji.set(emoji)
        await ctx.send(f"Emoji has been set to {emoji}")

    @jobs.command(name='posters')
    @commands.has_guild_permissions(administrator=True)
    async def set_create_role(self, ctx, role: discord.Role):
        """Set the role allowed to create jobs"""
        async with self.config.guild(ctx.guild).roles() as roles:
            roles[str(role.id)] = "create"
        await ctx.send(f"Role {role.name} can now create jobs.")

    @jobs.command(name='seekers')
    @commands.has_guild_permissions(administrator=True)
    async def set_take_role(self, ctx, role: discord.Role):
        """Set the role allowed to take jobs"""
        async with self.config.guild(ctx.guild).roles() as roles:
            roles[str(role.id)] = "take"
        await ctx.send(f"Role {role.name} can now take jobs.")

    @commands.command(name='job')
    async def add_job_slash(self, ctx: commands.Context, title: str, salary: int, description: str, 
                        image: Optional[str] = None, color: Optional[str] = None):
        """Create a new job posting"""
        await self.add_job(ctx, title, salary, description, image, color)

    @jobs.command(name='add')
    async def add_job_message(self, ctx: commands.Context, title: str, salary: int, description: str, 
                          image: Optional[str] = None, color: Optional[str] = None):
        """Create a new job posting"""
        await self.add_job(ctx, title, salary, description, image, color)

    async def add_job(self, ctx: commands.Context, title: str, salary: int, description: str,
                    image: Optional[str] = None, color: Optional[str] = None):
        """Helper function to create a job"""
        if not await self._can_create(ctx.author):
            await ctx.send("You do not have permission to create jobs", ephemeral=True)
            return

        creator_balance = await bank.get_balance(ctx.author)
        if creator_balance < salary:
            await ctx.send("You do not have enough funds to post this job", ephemeral=True)
            return

        await bank.withdraw_credits(ctx.author, salary)

        job_id = ctx.message.id

        async with self.config.guild(ctx.guild).jobs() as jobs:
            jobs[str(job_id)] = {
                "creator": ctx.author.id,
                "taker": None,
                "salary": salary,
                "description": description,
                "status": "open",
                "color": color,
                "image_url": image
            }

        default_color = getattr(discord.Colour, color, discord.Embed.Empty) if color is not None else discord.Embed.Empty

        embed = discord.Embed(
            title=f"{title} #{job_id}",
            description=description,
            colour=default_color
        )
        embed.add_field(name="Salary", value=str(salary))
        embed.add_field(name="Taken by", value="Not yet taken")

        if image:
            embed.set_image(url=image)

        job_channel_id = await self.config.guild(ctx.guild).job_channel_id()
        job_channel = self.bot.get_channel(job_channel_id)
        job_message = await job_channel.send(embed=embed)
        thread = await job_message.create_thread(name=f"{title} #{job_id} Discussion")

        async with self.config.guild(ctx.guild).jobs() as jobs:
            job = jobs[str(job_id)]
            job["thread_id"] = thread.id
            await job_message.add_reaction(await self.config.guild(ctx.guild).emoji())
            job["message_id"] = job_message.id

        job_done_button = discord.ui.Button(style=discord.ButtonStyle.SUCCESS, label="Job Done", custom_id=f"job_done_{job_id}")
        await job_message.edit(components=[job_done_button])

        await ctx.send(f"Job created with ID {job_id}", ephemeral=True)

    @commands.Cog.listener()
    async def on_component(self, ctx):
        if ctx.custom_id.startswith("job_done_"):
            await self.job_done_button_click(ctx)

    async def job_done_button_click(self, ctx):
        job_id = int(ctx.custom_id.split("_")[-1])

        async with self.config.guild(ctx.guild).jobs() as jobs:
            job = jobs.get(str(job_id))
            if not job or job["status"] != "in_progress" or ctx.author.id != job["creator"] and not ctx.author.guild_permissions.administrator:
                return

            taker = ctx.guild.get_member(job["taker"])
            if not taker:
                return

            await bank.deposit_credits(taker, job["salary"])
            job["status"] = "complete"

            thread = ctx.guild.get_thread(job["thread_id"])
            if thread:
                await thread.send("Job has been marked as complete.")

            job_message = await ctx.channel.fetch_message(job["message_id"])
            if job_message:
                embed = job_message.embeds[0]
                embed.color = Colour.green()
                await job_message.edit(embed=embed)
                job_done_button = Button(style=ButtonStyle.SUCCESS, label="Job Done", custom_id=f"job_done_{job_id}")
                await job_message.remove_components(job_done_button)

            await ctx.send("Job has been marked as complete.")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        emoji = await self.config.guild(self.bot.get_guild(payload.guild_id)).emoji()
        if payload.emoji.name == emoji:
            await self._handle_take_job_reaction(payload)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        emoji = await self.config.guild(self.bot.get_guild(payload.guild_id)).emoji()
        if payload.emoji.name == emoji:
            await self._handle_untake_job_reaction(payload)

    async def _handle_take_job_reaction(self, payload):
        job_channel_id = await self.config.guild(self.bot.get_guild(payload.guild_id)).job_channel_id()
        if payload.channel_id != job_channel_id:
            return

        async with self.config.guild(payload.guild).jobs() as jobs:
            job = jobs.get(str(payload.message_id))
            if not job or job["status"] != "open":
                return

            member = payload.member
            if await self._can_take(member):
                job["taker"] = member.id
                job["status"] = "in_progress"

                thread = member.guild.get_thread(job["thread_id"])
                if thread:
                    await thread.send(f"{member.mention} has taken the job.")

                job_message = await self.bot.get_channel(job_channel_id).fetch_message(payload.message_id)
                embed = job_message.embeds[0]
                embed.set_field_at(1, name="Taken by", value=member.mention)
                await job_message.edit(embed=embed)

    async def _handle_untake_job_reaction(self, payload):
        job_channel_id = await self.config.guild(self.bot.get_guild(payload.guild_id)).job_channel_id()
        if payload.channel_id != job_channel_id:
            return

        async with self.config.guild(payload.guild).jobs() as jobs:
            job = jobs.get(str(payload.message_id))
            if not job or job["status"] != "in_progress" or payload.user_id != job["taker"]:
                return

            member = self.bot.get_guild(payload.guild_id).get_member(payload.user_id)
            job["taker"] = None
            job["status"] = "open"

            thread = member.guild.get_thread(job["thread_id"])
            if thread:
                await thread.send(f"{member.mention} has untaken the job.")

            job_message = await self.bot.get_channel(job_channel_id).fetch_message(payload.message_id)
            embed = job_message.embeds[0]
            embed.set_field_at(1, name="Taken by", value="Not yet taken")
            await job_message.edit(embed=embed)

    async def _can_create(self, member):
        role_ids = [role.id for role in member.roles]
        async with self.config.guild(member.guild).roles() as roles:
            create_role_id = next((role_id for role_id in role_ids if roles.get(str(role_id)) == "create"), None)
        return create_role_id is not None

    async def _can_take(self, member):
        role_ids = [role.id for role in member.roles]
        async with self.config.guild(member.guild).roles() as roles:
            take_role_id = next((role_id for role_id in role_ids if roles.get(str(role_id)) == "take"), None)
        return take_role_id is not None

    async def cog_added(self):
        await self.bot.load_application_commands()
