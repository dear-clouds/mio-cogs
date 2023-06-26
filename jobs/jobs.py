import discord
from redbot.core import commands, app_commands, Config
from discord import Embed, Colour, Button, ButtonStyle
from typing import Optional

class Jobs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.job_channel_id = None
        self.roles = {}
        self.jobs = {}
        self.emoji = "\U0001F4BC"  # default emoji

    @commands.Cog.listener()
    async def on_ready(self):
        print("Jobs Cog has been loaded")

    @commands.group(invoke_without_command=True)
    async def jobs(self, ctx):
        """Manage jobs"""
        cmd = self.bot.get_command('jobs')
        subcommands = ""
        for sub in cmd.commands:
            subcommands += f"{sub.name} - {sub.help}\n"
        await ctx.send(subcommands)

    @jobs.command(name='channel')
    @commands.has_guild_permissions(administrator=True)
    async def set_channel(self, ctx, channel: discord.TextChannel):
        """Set the channel for jobs"""
        self.job_channel_id = channel.id
        await ctx.send(f"Job channel has been set to {channel.mention}")

    @jobs.command(name='emoji')
    @commands.has_guild_permissions(administrator=True)
    async def set_emoji(self, ctx, emoji: str):
        """Set the emoji for job reactions"""
        self.emoji = emoji
        await ctx.send(f"Emoji has been set to {emoji}")
    
    @jobs.command(name='posters')
    @commands.has_guild_permissions(administrator=True)
    async def set_create_role(self, ctx, role: discord.Role):
        """Set the role allowed to create jobs"""
        self.roles.setdefault(ctx.guild.id, {})[role.id] = "create"
        await ctx.send(f"Role {role.name} can now create jobs.")

    @jobs.command(name='seekers')
    @commands.has_guild_permissions(administrator=True)
    async def set_take_role(self, ctx, role: discord.Role):
        """Set the role allowed to take jobs"""
        self.roles.setdefault(ctx.guild.id, {})[role.id] = "take"
        await ctx.send(f"Role {role.name} can now take jobs.")

    @app_commands.command(name='job')
    async def add_job_slash(self, ctx: commands.Context, title: str, salary: int, description: str, 
                        image: Optional[str] = None, color: Optional[str] = None):
        """Create a new job posting"""
        await self.add_job(ctx, title, salary, description, image, color)

    @jobs.command(name='add')
    async def add_job_message(self, ctx: commands.Context, title: str, salary: int, description: str, 
                            image: Optional[str] = None, color: Optional[str] = None):
        """Create a new job posting"""
        await self.add_job(ctx, title, salary, description, image, color)


    async def add_job(self, interaction: discord.Interaction, title: str, salary: int, description: str, 
                    image: Optional[str] = None, color: Optional[str] = None):
        """Helper function to create a job"""

        if not self._can_create(interaction.user):
            await interaction.response.send_message("You do not have permission to create jobs", ephemeral=True)
            return

        job_id = interaction.id
        self.jobs[job_id] = {
            "creator": interaction.user.id,
            "taker": None,
            "salary": salary,
            "description": description,
            "status": "open",
            "color": color,
            "image_url": image
        }

        embed = Embed(title=f"{title} #{job_id}", description=description, colour=getattr(Colour, color)() if hasattr(Colour, color) else Colour.blue())
        embed.add_field(name="Salary", value=str(salary))
        embed.add_field(name="Taken by", value="Not yet taken")

        if image:
            embed.set_image(url=image)

        job_channel = self.bot.get_channel(self.job_channel_id)
        job_message = await job_channel.send(embed=embed)
        thread = await job_message.create_thread(name=f"{title} #{job_id} Discussion")
        self.jobs[job_id]["thread_id"] = thread.id
        await job_message.add_reaction(self.emoji)
        self.jobs[job_id]["message_id"] = job_message.id

        job_done_button = Button(style=ButtonStyle.SUCCESS, label="Job Done", custom_id=f"job_done_{job_id}")
        await job_message.edit(components=[job_done_button])

        await interaction.response.send_message(f"Job created with ID {job_id}", ephemeral=True)

    @commands.Cog.listener()
    async def on_component(self, ctx):
        if ctx.custom_id.startswith("job_done_"):
            await self.job_done_button_click(ctx)

    async def job_done_button_click(self, ctx):
        job_id = int(ctx.custom_id.split("_")[-1])
        job = self.jobs.get(job_id)
        if not job or job["status"] != "in_progress" or ctx.author.id != job["creator"] and not ctx.author.guild_permissions.administrator:
            return

        economy = self.bot.get_cog('Economy')
        if not economy:
            return

        taker = ctx.guild.get_member(job["taker"])
        if not taker:
            return

        economy.bank.deposit_credits(taker, job["salary"])
        job["status"] = "complete"

        thread = ctx.guild.get_thread(job["thread_id"])
        if thread:
            await thread.send("Job has been marked as complete.")
            if thread.type == ThreadType.Public and not thread.archived:
                await thread.archive()

        job_message = await ctx.channel.fetch_message(job["message_id"])
        if job_message:
            embed = job_message.embeds[0]
            embed.color = Colour.green()
            await job_message.edit(embed=embed)
            await job_message.remove_components(job_done_button)

        await ctx.send("Job has been marked as complete.")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.emoji.name == self.emoji:
            await self._handle_take_job_reaction(payload)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        if payload.emoji.name == self.emoji:
            await self._handle_untake_job_reaction(payload)

    async def _handle_take_job_reaction(self, payload):
        if payload.channel_id != self.job_channel_id or payload.message_id not in self.jobs:
            return

        job = self.jobs[payload.message_id]
        if job["status"] != "open":
            return

        member = payload.member
        if self._can_take(member):
            job["taker"] = member.id
            job["status"] = "in_progress"

            thread = member.guild.get_thread(job["thread_id"])
            if thread:
                await thread.send(f"{member.mention} has taken the job.")

            job_message = await self.bot.get_channel(self.job_channel_id).fetch_message(payload.message_id)
            embed = job_message.embeds[0]
            embed.set_field_at(1, name="Taken by", value=member.mention)
            await job_message.edit(embed=embed)

    async def _handle_untake_job_reaction(self, payload):
        if payload.channel_id != self.job_channel_id or payload.message_id not in self.jobs:
            return

        job = self.jobs[payload.message_id]
        if job["status"] != "in_progress" or payload.user_id != job["taker"]:
            return

        member = self.bot.get_guild(payload.guild_id).get_member(payload.user_id)
        job["taker"] = None
        job["status"] = "open"

        thread = member.guild.get_thread(job["thread_id"])
        if thread:
            await thread.send(f"{member.mention} has untaken the job.")

        job_message = await self.bot.get_channel(self.job_channel_id).fetch_message(payload.message_id)
        embed = job_message.embeds[0]
        embed.set_field_at(1, name="Taken by", value="Not yet taken")
        await job_message.edit(embed=embed)

    def _can_create(self, member):
        role_ids = [role.id for role in member.roles]
        create_role_id = self.roles.get(member.guild.id, {}).get("create")
        return create_role_id in role_ids

    def _can_take(self, member):
        role_ids = [role.id for role in member.roles]
        take_role_id = self.roles.get(member.guild.id, {}).get("take")
        return take_role_id in role_ids
    
    async def cog_added(self):
        await self.bot.load_application_commands()

def setup(bot):
    bot.add_cog(Jobs(bot))


