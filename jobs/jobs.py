import discord
from redbot.core import commands, Config, bank, app_commands
from typing import Optional
import datetime

class Jobs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1995987654322)
        default_guild = {
        "job_channel_id": None,
        "poster_roles": [],
        "seeker_roles": [],
        "jobs": {}
        }
        self.config.register_guild(**default_guild)

    @commands.group()
    @commands.guild_only()
    async def jobs(self, ctx):
        """Manage jobs"""
        pass

    @jobs.command(name='reset')
    @commands.has_guild_permissions(administrator=True)
    async def reset_config(self, ctx):
        """Reset the job configuration for this server."""
        await self.config.guild(ctx.guild).clear()
        await ctx.send("Cog configuration has been reset for this server.")

    @jobs.command(name='channel')
    @commands.has_guild_permissions(administrator=True)
    async def set_channel(self, ctx, channel: discord.TextChannel):
        """Set the channel for jobs"""
        await self.config.guild(ctx.guild).job_channel_id.set(channel.id)
        await ctx.send(f"Job channel has been set to {channel.mention}")

    @jobs.command(name='posters')
    @commands.has_guild_permissions(administrator=True)
    async def set_create_roles(self, ctx, *roles: discord.Role):
        """Add one or more roles to the list of roles allowed to create jobs"""
        if not roles:
            await ctx.send("Please mention one or more roles to add.")
            return

        async with self.config.guild(ctx.guild).poster_roles() as poster_roles:
            for role in roles:
                if role.id not in poster_roles:
                    poster_roles.append(role.id)
        
        role_mentions = ", ".join(role.mention for role in roles)
        await ctx.send(f"Roles {role_mentions} can now create jobs.")

    @jobs.command(name='seekers')
    @commands.has_guild_permissions(administrator=True)
    async def set_take_roles(self, ctx, *roles: discord.Role):
        """Add one or more roles to the list of roles allowed to take jobs"""
        if not roles:
            await ctx.send("Please mention one or more roles to add.")
            return

        async with self.config.guild(ctx.guild).seeker_roles() as seeker_roles:
            for role in roles:
                if role.id not in seeker_roles:
                    seeker_roles.append(role.id)
        
        role_mentions = ", ".join(role.mention for role in roles)
        await ctx.send(f"Roles {role_mentions} can now take jobs.")

    async def can_create(self, member):
        """Check if the member can create jobs."""
        async with self.config.guild(member.guild).poster_roles() as poster_roles:
            return any(role.id in poster_roles for role in member.roles)

    async def can_take(self, member):
        """Check if the member can take jobs."""
        async with self.config.guild(member.guild).seeker_roles() as seeker_roles:
            return any(role.id in seeker_roles for role in member.roles)

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
                "image_url": image,
                "completed": False
            }

        if color:
            if color.startswith('#'):
                color_value = int(color[1:], 16)
                default_color = discord.Colour(color_value)
            else:
                default_color = getattr(discord.Colour, color, await context.embed_colour())
        else:
            default_color = await context.embed_colour()

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

        # Set the footer with poster's avatar and post date
        embed.set_footer(
            text=f"Job posted by {author.display_name} on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            icon_url=author.avatar.url if author.avatar else None
        )

        # Send the job message with the embed and view
        job_channel_id = await self.config.guild(guild).job_channel_id()
        job_channel = self.bot.get_channel(job_channel_id)

        view = JobView(self, job_id)
        job_message = await job_channel.send(embed=embed, view=view)
        view._message = job_message

        # Create the job's discussion thread and post the initial embed
        thread = await job_message.create_thread(name=f"{title}'s Discussion")
        await thread.send(embed=embed)

        async with self.config.guild(guild).jobs() as jobs:
            job = jobs[str(job_id)]
            job["thread_id"] = thread.id
            job["message_id"] = job_message.id

        await context.send(f"Job created with ID {job_id}", ephemeral=True)

class JobView(discord.ui.View):
    def __init__(self, jobs_cog, job_id: int):
        super().__init__(timeout=None)
        self.jobs_cog = jobs_cog
        self.job_id = job_id
        self._message = None

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

    @discord.ui.button(label="Apply", emoji="💼", style=discord.ButtonStyle.primary)
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

            # Update the message embed and disable the apply button
            embed = self._message.embeds[0]
            embed.set_field_at(1, name="Taken by", value=taker.mention)
            self.children[0].disabled = True  # Apply button
            self.children[1].disabled = False  # Untake button
            self.children[2].disabled = False  # Job done button
            await self._message.edit(embed=embed, view=self)

            await interaction.response.send_message("You have successfully applied for the job.", ephemeral=True)

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

    @discord.ui.button(label="Mark job as done", emoji="✔️", style=discord.ButtonStyle.green, disabled=True)
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
            taker_id = job["taker"]
            taker = guild.get_member(taker_id)
            # Pay the taker
            if taker:
                await bank.deposit_credits(taker, job["salary"])

            # Set the job as completed
            job["completed"] = True

            # Delete the initial message with buttons
            try:
                await self._message.delete()
            except discord.NotFound:
                pass

            # Send a message in the job's thread with a green-colored embed
            thread = guild.get_thread(job["thread_id"])
            creator = guild.get_member(job["creator"])
            if thread:
                embed = self._message.embeds[0]
                embed.color = discord.Colour.green()
                await thread.send(embed=embed)
                await thread.send(f"{creator.mention} has marked the job as complete and credits has been sent to {taker.mention}.")

        await interaction.response.send_message("Job has been marked as complete.", ephemeral=True)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await self.jobs_cog.can_create(interaction.user)

    @discord.ui.button(label="Post a job", emoji="➕", style=discord.ButtonStyle.secondary)
    async def post_job_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Ensure that the user has the permission to create a job
        if not await self.jobs_cog.can_create(interaction.user):
            await interaction.response.send_message("You do not have permission to post a job.", ephemeral=True)
            return

        # Send the modal to the user
        modal = JobPostModal(self.jobs_cog)
        await interaction.response.send_modal(modal)
            
class JobPostModal(discord.ui.Modal, title="Post a New Job"):
    def __init__(self, jobs_cog):
        super().__init__()
        self.jobs_cog = jobs_cog

    job_title = discord.ui.TextInput(
        label="Job Title",
        placeholder="Enter the job title here...",
        required=True,
        min_length=5,
        max_length=100
    )

    salary = discord.ui.TextInput(
        label="Salary",
        placeholder="Enter the salary here...",
        style=discord.TextStyle.short,
        required=True,
    )

    description = discord.ui.TextInput(
        label="Description",
        placeholder="Enter the job description here...",
        style=discord.TextStyle.paragraph,
        required=True,
        min_length=10,
        max_length=2000
    )

    image_url = discord.ui.TextInput(
        label="Image URL (optional)",
        placeholder="Enter an image URL...",
        required=False,  # This field is optional
        max_length=2048  # Maximum length for URLs
    )

    embed_color = discord.ui.TextInput(
        label="Embed Color (optional)",
        placeholder="Enter a hexa color code...",
        required=False,  # This field is optional
        max_length=7  # Length of a hex color code including #
    )

    async def on_submit(self, interaction: discord.Interaction):
        job_title = self.job_title.value
        salary_str = self.salary.value
        description = self.description.value
        image = self.image_url.value
        color_str = self.embed_color.value

        # Validate salary
        try:
            salary = int(salary_str)
            if salary <= 0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message("Invalid salary. Please enter a positive number.", ephemeral=True)
            return

        # Validate color, if provided
        color = None
        if color_str:
            if not color_str.startswith('#') or len(color_str) != 7:
                await interaction.response.send_message("Invalid color code. Please enter a hex code like #FF5733.", ephemeral=True)
                return
            try:
                color = int(color_str[1:], 16)
            except ValueError:
                await interaction.response.send_message("Invalid color code. Please enter a valid hex code.", ephemeral=True)
                return

        # Use the add_job method to create a new job
        await self.jobs_cog.add_job(interaction, job_title, salary, description, image, color_str)

        await interaction.response.send_message(f"Job '{job_title}' created successfully!", ephemeral=True)
