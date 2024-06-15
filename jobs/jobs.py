import discord
from discord.ext import tasks
from redbot.core import commands, Config, bank, app_commands
from typing import Optional
import datetime
import math

class Jobs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1995987654322)
        default_guild = {
            "job_channel_id": None,
            "poster_roles": [],
            "seeker_roles": [],
            "jobs": {},
            "thumb_done": "https://i.imgur.com/0YBdp8p.png"
        }
        default_user = {"jobs_posted": 0, "jobs_taken": 0}
        self.config.register_user(**default_user)
        self.config.register_guild(**default_guild)
        bot.add_view(JobView(self, None))  # Registering the view as persistent
        self.refresh_views.start()  # Start the view refresh task

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
        
    @jobs.command(name='setimage')
    @commands.has_guild_permissions(administrator=True)
    async def set_completed_job_image(self, ctx, image_url: str):
        """Set the custom image for completed job embeds"""
        await self.config.guild(ctx.guild).thumb_done.set(image_url)
        await ctx.send(f"Custom image for completed jobs has been set.")
        
    @jobs.command(name='showconfig')
    @commands.has_guild_permissions(administrator=True)
    async def show_config(self, ctx):
        """Show the current configuration of the Jobs cog for this server."""
        config_data = await self.config.guild(ctx.guild).all()

        embed = discord.Embed(
            title="Current Jobs Cog Configuration",
        )

        job_channel_id = config_data.get("job_channel_id")
        job_channel = f"<#{job_channel_id}>" if job_channel_id else "Not Set"

        poster_roles = ", ".join([f"<@&{role_id}>" for role_id in config_data.get("poster_roles", [])])
        seeker_roles = ", ".join([f"<@&{role_id}>" for role_id in config_data.get("seeker_roles", [])])
        thumb_done_url = config_data.get("thumb_done", "Not Set")

        embed.add_field(name="Job Channel", value=job_channel, inline=False)
        embed.add_field(name="Poster Roles", value=poster_roles if poster_roles else "None", inline=False)
        embed.add_field(name="Seeker Roles", value=seeker_roles if seeker_roles else "None", inline=False)
        embed.set_thumbnail(url=thumb_done_url)

        await ctx.send(embed=embed)
        
    @commands.group()
    async def jobstats(self, ctx, user: Optional[discord.Member] = None):
        """Show job stats for a user. Admins can view stats for any user."""
        if not user:
            user = ctx.author

        if user != ctx.author and not ctx.channel.permissions_for(ctx.author).administrator:
            await ctx.send("You do not have permission to view other users' job stats.")
            return

        user_data = await self.config.user(user).all()
        jobs_posted = user_data.get("jobs_posted", 0)
        jobs_taken = user_data.get("jobs_taken", 0)
        default_color = await ctx.embed_color()
        
        # Initialize lists to store thread links
        posted_job_links = []
        taken_job_links = []

        async with self.config.guild(ctx.guild).jobs() as jobs:
            for job_id, job in jobs.items():
                if job["thread_id"]:
                    thread = ctx.guild.get_thread(job["thread_id"])
                    if thread:
                        job_link = f"- [{thread.name}]({thread.jump_url})"
                        if job["creator"] == user.id:
                            posted_job_links.append(job_link)
                        elif job.get("taker") == user.id and job.get("completed"):
                            taken_job_links.append(job_link)

        # Create embeds for pagination if necessary
        embeds = []
        if len(posted_job_links) > 20 or len(taken_job_links) > 20:
            for i in range(0, max(len(posted_job_links), len(taken_job_links)), 20):
                embed = discord.Embed(title=f"💼 {user.display_name}'s Job Stats", color=default_color)
                embed.add_field(name=f"Jobs Posted ({len(posted_job_links)})", value="\n".join(posted_job_links[i:i+20]), inline=True)
                embed.add_field(name=f"Jobs Completed ({len(taken_job_links)})", value="\n".join(taken_job_links[i:i+20]), inline=True)
                embeds.append(embed)

            # Start the paginator
            paginator = Paginator(ctx, embeds)
            await paginator.start()
        else:
            # Single embed if pagination is not needed
            embed = discord.Embed(title=f"💼 {user.display_name}'s Job Stats", color=default_color)
            embed.add_field(name=f"Jobs Posted ({len(posted_job_links)})", value="\n".join(posted_job_links), inline=True)
            embed.add_field(name=f"Jobs Completed ({len(taken_job_links)})", value="\n".join(taken_job_links), inline=True)
            await ctx.send(embed=embed)
            
    @tasks.loop(minutes=10)  # Run this task every 10 minutes
    async def refresh_views(self):
        """Refresh views on existing job posts to keep them active."""
        for guild in self.bot.guilds:
            job_channel_id = await self.config.guild(guild).job_channel_id()
            if not job_channel_id:
                continue

            job_channel = guild.get_channel(job_channel_id)
            if not job_channel:
                continue

            async with self.config.guild(guild).jobs() as jobs:
                for job_id, job_data in jobs.items():
                    message_id = job_data.get("message_id")
                    if not message_id:
                        continue

                    try:
                        job_message = await job_channel.fetch_message(message_id)
                        if not job_message:
                            continue

                        view = JobView(self, job_id=int(job_id))
                        view._message = job_message
                        job_status = job_data.get("status", "open")
                        job_taker = job_data.get("taker")

                        # Disable/enable buttons based on job status
                        for item in view.children:
                            if isinstance(item, discord.ui.Button):
                                if item.custom_id == "apply_button":
                                    item.disabled = job_status != "open"
                                elif item.custom_id == "untake_button":
                                    item.disabled = job_status != "in_progress" or job_taker != job_message.author.id
                                elif item.custom_id == "job_done_button":
                                    item.disabled = job_status != "in_progress"

                        await job_message.edit(view=view)
                    except discord.NotFound:
                        continue

    @commands.Cog.listener()
    async def on_ready(self):
        self.refresh_views.start()  # Start the task when the bot is ready

    @app_commands.command(name='job')
    async def add_job_slash(self, interaction: discord.Interaction, title: str, salary: int, description: str,
                            image: Optional[str] = None, color: Optional[str] = None):
        """Create a new job posting"""
        await self.add_job(interaction, title, salary, description, image, color)

    @jobs.command(name='add')
    async def add_job_message(self, ctx: commands.Context, title: str, salary: int, description: str, image: Optional[str] = None, color: Optional[str] = None):
        """Create a new job posting"""
        await self.add_job(ctx, title, salary, description, image, color)

    async def add_job(self, context, title: str, salary: int, description: str, image: Optional[str] = None, color: Optional[str] = None):
        """Helper function to create a job"""
        if isinstance(context, commands.Context):
            author = context.author
            guild = context.guild
            job_id = context.message.id
            default_color = await context.embed_colour()
            send_method = context.send
        elif isinstance(context, discord.Interaction):
            author = context.user
            guild = context.guild
            job_id = context.id
            default_color = await self.config.guild(guild).default_embed_color()
            send_method = context.response.send_message
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
                default_color = getattr(discord.Colour, color, default_color)
                
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
            text=f"Job posted by {author.display_name} on {datetime.datetime.now().strftime('%B %d, %Y')}",
            icon_url=author.avatar.url if author.avatar else None
        )

        # Send the job message with the embed and view
        job_channel_id = await self.config.guild(guild).job_channel_id()
        job_channel = self.bot.get_channel(job_channel_id)

        view = JobView(self, job_id)
        job_message = await job_channel.send(embed=embed, view=view)
        view._message = job_message
        user_data = await self.config.user(author).all()
        jobs_posted = user_data.get("jobs_posted", 0) + 1
        await self.config.user(author).jobs_posted.set(jobs_posted)

        # Create the job's discussion thread and post the initial embed
        thread_title = f"{author.display_name}'s Job {jobs_posted:02}: {title}"
        thread = await job_message.create_thread(name=thread_title)
        await thread.send(embed=embed)

        async with self.config.guild(guild).jobs() as jobs:
            job = jobs[str(job_id)]
            job["thread_id"] = thread.id
            job["message_id"] = job_message.id

        await send_method(f"Job created with ID {job_id}", ephemeral=True)

class JobView(discord.ui.View):
    def __init__(self, jobs_cog, job_id: int):
        super().__init__(timeout=None)
        self.jobs_cog = jobs_cog
        self.job_id = job_id
        self._message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        job_id = self.job_id
        guild = interaction.guild

        async with self.jobs_cog.config.guild(guild).jobs() as jobs:
            job = jobs.get(str(job_id))
            if job and (job["creator"] == interaction.user.id or await self.jobs_cog.can_take(interaction.user)):
                return True
        return False

    @discord.ui.button(label="Apply", emoji="💼", style=discord.ButtonStyle.primary, custom_id="apply_button")
    async def apply_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        job_id = self.job_id
        taker = interaction.user
        guild = interaction.guild

        async with self.jobs_cog.config.guild(guild).jobs() as jobs:
            job = jobs.get(str(job_id))
            if not job or job["taker"]:
                await interaction.followup.send("This job has already been taken.", ephemeral=True)
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

            await interaction.followup.send("You have successfully applied for the job.", ephemeral=True)

    @discord.ui.button(label="Untake Job", style=discord.ButtonStyle.danger, custom_id="untake_button", disabled=True)
    async def untake_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        job_id = self.job_id
        taker = interaction.user
        guild = interaction.guild

        async with self.jobs_cog.config.guild(guild).jobs() as jobs:
            job = jobs.get(str(job_id))
            if not job or job["taker"] != taker.id:
                await interaction.followup.send("You cannot untake a job you haven't taken.", ephemeral=True)
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

        await interaction.followup.send("You have untaken the job.", ephemeral=True)

    @discord.ui.button(label="Mark job as done", emoji="✔️", style=discord.ButtonStyle.green, custom_id="job_done_button", disabled=True)
    async def job_done_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        job_id = self.job_id
        user = interaction.user
        guild = interaction.guild

        async with self.jobs_cog.config.guild(guild).jobs() as jobs:
            job = jobs.get(str(job_id))
            if not job:
                await interaction.followup.send("Job not found.", ephemeral=True)
                return

            # Check if the user is the job creator
            if job["creator"] != user.id:
                await interaction.followup.send("You are not authorized to mark this job as done.", ephemeral=True)
                return

            if job["status"] != "in_progress":
                await interaction.followup.send("This job cannot be marked as done.", ephemeral=True)
                return

            # Mark the job as complete
            job["status"] = "complete"
            job["completed"] = True

            # Pay the taker if there is one
            taker_id = job.get("taker")
            if taker_id:
                taker = guild.get_member(taker_id)
                if taker:
                    taker_data = await self.jobs_cog.config.user(taker).all()
                    jobs_taken = taker_data.get("jobs_taken", 0) + 1
                    await self.jobs_cog.config.user(taker).jobs_taken.set(jobs_taken)
                    await bank.deposit_credits(taker, job["salary"])

                # Delete the initial message with buttons
                try:
                    await self._message.delete()
                except discord.NotFound:
                    pass

                # Send a message in the job's thread with a green-colored embed
                completed_image_url = await self.jobs_cog.config.guild(guild).thumb_done()
                thread = guild.get_thread(job["thread_id"])
                creator = guild.get_member(job["creator"])
                if thread:
                    embed = self._message.embeds[0]
                    embed.color = discord.Colour.green()
                    embed.set_thumbnail(url=completed_image_url)
                    await thread.send(embed=embed)
                    await thread.send(f"{creator.mention} has marked the job as complete and the salary has been sent to {taker.mention}.")

        await interaction.followup.send("Job has been marked as complete.", ephemeral=True)

    @discord.ui.button(label="Post a job", emoji="➕", style=discord.ButtonStyle.secondary, custom_id="post_job")
    async def post_job_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        # Ensure that the user has the permission to create a job
        if not await self.jobs_cog.can_create(interaction.user):
            await interaction.followup.send("You do not have permission to post a job.", ephemeral=True)
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
        placeholder="Enter the job title here.",
        required=True,
        min_length=5,
        max_length=100
    )

    salary = discord.ui.TextInput(
        label="Salary",
        placeholder="The amount will be withdrawn immediately after submission.",
        style=discord.TextStyle.short,
        required=True,
    )

    description = discord.ui.TextInput(
        label="Description",
        placeholder="Describe the job here. You can use markdown.",
        style=discord.TextStyle.paragraph,
        required=True,
        min_length=10,
        max_length=2000
    )

    image_url = discord.ui.TextInput(
        label="Image URL (optional)",
        placeholder="Enter an image URL.",
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
            await interaction.followup.send("Invalid salary. Please enter a positive number.", ephemeral=True)
            return

        # Validate color, if provided
        color = None
        if color_str:
            if not color_str.startswith('#') or len(color_str) != 7:
                await interaction.followup.send("Invalid color code. Please enter a hex code like #FF5733.", ephemeral=True)
                return
            try:
                color = int(color_str[1:], 16)
            except ValueError:
                await interaction.followup.send("Invalid color code. Please enter a valid hex code.", ephemeral=True)
                return

        # Use the add_job method to create a new job
        await self.jobs_cog.add_job(interaction, job_title, salary, description, image, color_str)

        await interaction.followup.send(f"Job '{job_title}' created successfully!", ephemeral=True)

class Paginator:
    def __init__(self, ctx, embeds):
        self.ctx = ctx
        self.embeds = embeds
        self.current_page = 0
        self.total_pages = len(embeds)

    async def start(self):
        self.message = await self.ctx.send(embed=self.embeds[self.current_page])
        await self.message.add_reaction("⬅️")
        await self.message.add_reaction("➡️")
        self.bot.loop.create_task(self.reaction_check())

    async def reaction_check(self):
        def check(reaction, user):
            return user == self.ctx.author and str(reaction.emoji) in ["⬅️", "➡️"]

        while True:
            try:
                reaction, user = await self.bot.wait_for("reaction_add", timeout=60.0, check=check)
                if str(reaction.emoji) == "➡️" and self.current_page < self.total_pages - 1:
                    self.current_page += 1
                    await self.message.edit(embed=self.embeds[self.current_page])
                elif str(reaction.emoji) == "⬅️" and self.current_page > 0:
                    self.current_page -= 1
                    await self.message.edit(embed=self.embeds[self.current_page])

                await self.message.remove_reaction(reaction, user)
            except asyncio.TimeoutError:
                await self.message.clear_reactions()
                break
