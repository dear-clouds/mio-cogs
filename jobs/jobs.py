import discord
from redbot.core import commands, Config, bank, app_commands
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

    @app_commands.command(name='job')
    async def add_job_slash(self, interaction: discord.Interaction, title: str, salary: int, description: str,
                            image: Optional[str] = None, color: Optional[str] = None):
        """Create a new job posting"""
        await self.add_job(interaction, title, salary, description, image, color)

    @jobs.command(name='add')
    async def add_job_message(self, ctx: commands.Context, title: str, salary: int, description: str,
                              image: Optional[str] = None, color: Optional[str] = None):
        """Create a new job posting"""
        await self.add_job(ctx, title, salary, description, image, color)

    async def add_job(self, context, title: str, salary: int, description: str,
                  image: Optional[str] = None, color: Optional[str] = None):
        """Helper function to create a job"""
        # Determine if context is from a slash command or text command
        if isinstance(context, commands.Context):
            author = context.author
            guild = context.guild
            job_id = context.message.id
        elif isinstance(context, discord.Interaction):
            author = context.user
            guild = context.guild
            job_id = context.id
        else:
            raise TypeError("Invalid context type")

        if not await self._can_create(author):
            await context.send("You do not have permission to create jobs", ephemeral=True)
            return

        currency_name = await bank.get_currency_name(guild=guild)
        creator_balance = await bank.get_balance(author)
        if creator_balance < salary:
            await context.send("You do not have enough credits to post this job", ephemeral=True)
            return

        await bank.withdraw_credits(author, salary)

        async with self.config.guild(guild).jobs() as jobs:
            jobs[str(job_id)] = {
                "creator": author.id,
                "taker": None,
                "salary": salary,
                "description": description,
                "status": "open",
                "color": color,
                "image_url": image
            }

        default_color = getattr(discord.Colour, color, await context.embed_colour()) if color is not None else await context.embed_colour()

        view = JobView(self, job_id)

        # Create and configure the embed
        embed = discord.Embed(
            title=f"{title}",
            description=description,
            colour=default_color
        )
        embed.add_field(name="Salary", value=f"{salary} {currency_name}")
        embed.add_field(name="Taken by", value="Not yet taken")
        if image:
            embed.set_image(url=image)

        # Send the job message with the embed and view
        job_channel_id = await self.config.guild(ctx.guild).job_channel_id()
        job_channel = self.bot.get_channel(job_channel_id)
        
        job_message = await job_channel.send(embed=embed, view=view)
        view._message = job_message  # Link the message to the view for later editing

        thread = await job_message.create_thread(name=f"{title}'s Discussion")

        async with self.config.guild(ctx.guild).jobs() as jobs:
            job = jobs[str(job_id)]
            job["thread_id"] = thread.id
            await job_message.add_reaction(await self.config.guild(ctx.guild).emoji())
            job["message_id"] = job_message.id

        await ctx.send(f"Job created with ID {job_id}", ephemeral=True)

    @commands.Cog.listener()
    async def on_component(self, ctx):
        if ctx.custom_id.startswith("job_done_"):
            await self.job_done_button_click(ctx)

    async def _can_create(self, member):
        role_ids = [role.id for role in member.roles]
        async with self.config.guild(member.guild).roles() as roles:
            create_role_id = next(
                (role_id for role_id in role_ids if roles.get(str(role_id)) == "create"), None)
        return create_role_id is not None

    async def _can_take(self, member):
        role_ids = [role.id for role in member.roles]
        async with self.config.guild(member.guild).roles() as roles:
            take_role_id = next(
                (role_id for role_id in role_ids if roles.get(str(role_id)) == "take"), None)
        return take_role_id is not None

    async def cog_added(self):
        await self.bot.load_application_commands()

    class JobView(discord.ui.View):
        def __init__(self, jobs_cog, job_id: int):
            super().__init__(timeout=180)
            self.jobs_cog = jobs_cog
            self.job_id = job_id
            self._message: discord.Message = None
            self.taker = None

            # Dynamically add the "Job Done" button with a specific custom_id
            self.add_item(discord.ui.Button(label="Job Done", style=discord.ButtonStyle.green, custom_id=f"job_done_{self.job_id}"))

        async def on_timeout(self) -> None:
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True
            if self._message is not None:
                try:
                    await self._message.edit(view=self)
                except discord.HTTPException:
                    pass

        async def _apply_for_job(self, interaction: discord.Interaction) -> None:
            if self.taker is not None:
                await interaction.response.send_message("This job is already taken.", ephemeral=True)
                return

            self.taker = interaction.user
            await self._update_job_status(interaction, "in_progress")

            await interaction.response.send_message("You have successfully applied for the job.", ephemeral=True)

        async def _untake_job(self, interaction: discord.Interaction) -> None:
            if self.taker != interaction.user:
                await interaction.response.send_message("You cannot untake a job you haven't taken.", ephemeral=True)
                return

            self.taker = None
            await self._update_job_status(interaction, "open")

            await interaction.response.send_message("You have untaken the job.", ephemeral=True)

        async def _update_job_status(self, interaction: discord.Interaction, status: str) -> None:
            guild = interaction.guild
            async with self.jobs_cog.config.guild(guild).jobs() as jobs:
                job = jobs.get(str(self.job_id))
                if not job:
                    return

                job["status"] = status
                job["taker"] = self.taker.id if self.taker else None

                thread = guild.get_thread(job["thread_id"])
                if thread:
                    action = "taken" if status == "in_progress" else "untaken"
                    await thread.send(f"{self.taker.mention} has {action} the job.")

                if self._message:
                    embed = self._message.embeds[0]
                    taker_text = self.taker.mention if self.taker else "Not yet taken"
                    embed.set_field_at(1, name="Taken by", value=taker_text)
                    await self._message.edit(embed=embed)

        @discord.ui.button(label="Apply", style=discord.ButtonStyle.success)
        async def apply_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
            await self._apply_for_job(interaction)

        @discord.ui.button(label="Untake Job", style=discord.ButtonStyle.danger)
        async def untake_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
            await self._untake_job(interaction)

        async def job_done_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            job_id = int(button.custom_id.split('_')[-1])
            guild = interaction.guild

            async with self.jobs_cog.config.guild(guild).jobs() as jobs:
                job = jobs.get(str(job_id))
                if not job or job["status"] != "in_progress" or self.taker != interaction.user:
                    await interaction.response.send_message("You cannot mark this job as done.", ephemeral=True)
                    return

                job["status"] = "complete"
                await bank.deposit_credits(self.taker, job["salary"])

                thread = guild.get_thread(job["thread_id"])
                if thread:
                    # Fetch the creator as a discord.Member object
                    creator = guild.get_member(job["creator"])
                    if creator and self.taker:
                        await thread.send(f"{creator.mention} has marked the job as complete and credit has been sent to {self.taker.mention}.")
                    else:
                        await thread.send("Job has been marked as complete and credit has been sent.")

                if self._message:
                    embed = self._message.embeds[0]
                    embed.color = discord.Colour.green()
                    await self._message.edit(embed=embed, view=self)

                await interaction.response.send_message("Job has been marked as complete.", ephemeral=True)
