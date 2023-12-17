import discord
from redbot.core import commands, Config, bank, app_commands
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
        
    async def can_create(self, member):
        """Check if the member can create jobs."""
        role_ids = [role.id for role in member.roles]
        async with self.config.guild(member.guild).roles() as roles:
            create_role_id = next((role_id for role_id in role_ids if roles.get(str(role_id)) == "create"), None)
        return create_role_id is not None

    async def can_take(self, member):
        """Check if the member can take jobs."""
        role_ids = [role.id for role in member.roles]
        async with self.config.guild(member.guild).roles() as roles:
            take_role_id = next((role_id for role_id in role_ids if roles.get(str(role_id)) == "take"), None)
        return take_role_id is not None

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

        if not await self.can_create(author):
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

        if color:
            if color.startswith('#'):
                color_value = int(color[1:], 16)
                default_color = discord.Colour(color_value)
            else:
                default_color = getattr(discord.Colour, color, await context.embed_colour())
        else:
            default_color = await context.embed_colour()

        apply_emoji = await self.config.guild(guild).emoji()
    
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
        job_channel_id = await self.config.guild(guild).job_channel_id()
        job_channel = self.bot.get_channel(job_channel_id)
        
        view = JobView(self, job_id, apply_emoji)
        job_message = await job_channel.send(embed=embed, view=view)
        view._message = job_message

        thread = await job_message.create_thread(name=f"{title}'s Discussion")

        async with self.config.guild(guild).jobs() as jobs:
            job = jobs[str(job_id)]
            job["thread_id"] = thread.id
            job["message_id"] = job_message.id

        await context.send(f"Job created with ID {job_id}", ephemeral=True)

class JobView(discord.ui.View):
    def __init__(self, jobs_cog, job_id: int, apply_emoji: str):
        super().__init__(timeout=180)
        self.jobs_cog = jobs_cog
        self.job_id = job_id
        self._message = None
        self.apply_emoji = apply_emoji

        # Create the "Apply" button with the emoji
        # self.add_item(discord.ui.Button(label=f"{self.apply_emoji} Apply", style=discord.ButtonStyle.primary, custom_id=f"apply_{job_id}"))

        # Create and add the "Untake Job" and "Mark job as done" buttons
        # They will be enabled or disabled based on job status
        # self.add_item(discord.ui.Button(label="Untake Job", style=discord.ButtonStyle.danger, custom_id=f"untake_{job_id}", disabled=True))
        # self.add_item(discord.ui.Button(label="Mark job as done", style=discord.ButtonStyle.green, custom_id=f"job_done_{job_id}", disabled=True))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Check if the user interacting with the button has the appropriate role
        return await self.jobs_cog.can_take(interaction.user)

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        if self._message is not None:
            try:
                await self._message.edit(view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="Apply", style=discord.ButtonStyle.primary)
    async def apply_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        job_id = self.job_id
        taker = interaction.user
        guild = interaction.guild

        async with self.jobs_cog.config.guild(guild).jobs() as jobs:
            job = jobs.get(str(job_id))
            if not job or job["taker"]:
                await interaction.response.send_message("This job has already been taken.", ephemeral=True)
                return

            job["taker"] = taker.id
            job["status"] = "in_progress"

            # Send a message in the job's thread
            thread = guild.get_thread(job["thread_id"])
            if thread:
                await thread.send(f"{taker.mention} has taken the job.")

        try:
            # Update the message embed and disable the apply button
            embed = self._message.embeds[0]
            embed.set_field_at(1, name="Taken by", value=taker.mention)
            self.children[0].disabled = True  # Apply button
            self.children[1].disabled = False  # Untake button
            self.children[2].disabled = False  # Job done button
            await self._message.edit(embed=embed, view=self)

            await interaction.response.send_message("You have successfully applied for the job.", ephemeral=True)
        except Exception as e:
            # Log the error for debugging and acknowledge the interaction
            print(f"Error in apply_button: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("An error occurred.", ephemeral=True)

    @discord.ui.button(label="Untake Job", style=discord.ButtonStyle.danger, disabled=True)
    async def untake_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        job_id = self.job_id
        taker = interaction.user
        guild = interaction.guild

        async with self.jobs_cog.config.guild(guild).jobs() as jobs:
            job = jobs.get(str(job_id))
            if not job or job["taker"] != taker.id:
                await interaction.response.send_message("You cannot untake a job you haven't taken.", ephemeral=True)
                return

            job["taker"] = None
            job["status"] = "open"

            # Send a message in the job's thread
            thread = guild.get_thread(job["thread_id"])
            if thread:
                await thread.send(f"{taker.mention} has untaken the job.")

        # Update the message embed and enable the apply button
        embed = self._message.embeds[0]
        embed.set_field_at(1, name="Taken by", value="Not yet taken")
        self.children[0].disabled = False  # Apply button
        self.children[1].disabled = True   # Untake button
        self.children[2].disabled = True   # Job done button
        await self._message.edit(embed=embed, view=self)

        await interaction.response.send_message("You have untaken the job.", ephemeral=True)

    @discord.ui.button(label="Mark job as done", style=discord.ButtonStyle.green, disabled=True)
    async def job_done_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        job_id = self.job_id
        taker = interaction.user
        guild = interaction.guild

        async with self.jobs_cog.config.guild(guild).jobs() as jobs:
            job = jobs.get(str(job_id))
            if not job or job["taker"] != taker.id or job["status"] != "in_progress":
                await interaction.response.send_message("You cannot mark this job as done.", ephemeral=True)
                return

            job["status"] = "complete"
            await bank.deposit_credits(discord.Object(id=job["taker"]), job["salary"])

            # Send a message in the job's thread
            thread = guild.get_thread(job["thread_id"])
            creator = guild.get_member(job["creator"])
            if thread:
                await thread.send(f"{creator.mention} has marked the job as complete and credit has been sent to {taker.mention}.")

        # Update the message embed to reflect completion
        embed = self._message.embeds[0]
        embed.color = discord.Colour.green()
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        await self._message.edit(embed=embed, view=self)

        await interaction.response.send_message("Job has been marked as complete.", ephemeral=True)

    # Add the callback methods to their respective buttons
    # def add_item(self, item):
    #     if isinstance(item, discord.ui.Button):
    #         if item.custom_id.startswith("apply_"):
    #             item.callback = self.apply_button
    #         elif item.custom_id.startswith("untake_"):
    #             item.callback = self.untake_button
    #         elif item.custom_id.startswith("job_done_"):
    #             item.callback = self.job_done_button
    #     super().add_item(item)