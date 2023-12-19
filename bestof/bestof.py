import discord
import plexapi
import asyncio
from redbot.core import commands, Config, app_commands
from discord.ui import View, Select
from plexapi.server import PlexServer
from datetime import datetime
from typing import Optional

class BestOf(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=199523456789)
        self.config.register_global(
            plex_server_url=None,
            plex_server_auth_token=None,
            allowed_libraries=[]
        )
        self.config.register_user(votes={})
        self.plex = None

    async def cog_load(self):
        await self.initialize()

    async def initialize(self):
        await self.bot.wait_until_ready()
        plex_server_url = await self.config.plex_server_url()
        plex_server_auth_token = await self.config.plex_server_auth_token()
        
        try:
            self.plex = PlexServer(plex_server_url, plex_server_auth_token)
            self.server_name = self.plex.friendlyName
        except Exception as e:
            print(f"Failed to connect to Plex server: {e}")

    @commands.group(autohelp=True)
    @commands.guild_only()
    @commands.is_owner()
    async def bestof(self, ctx):
        """BestOf settings."""
        pass

    @bestof.command(name="url")
    async def set_url(self, ctx, url: str):
        """Sets the Plex server URL."""
        await self.config.plex_server_url.set(url)
        await ctx.send(f"Plex server URL set to {url}. You can test the connection with the `test` command.")

    @bestof.command(name="token")
    async def set_token(self, ctx, token: str):
        """Sets the Plex server authentication token."""
        await self.config.plex_server_auth_token.set(token)
        await ctx.send(f"Plex token set to `{token}`. You can test the connection with the `test` command.")
        
    @bestof.command(name="test")
    async def test(self, ctx):
        """Test the connection to the Plex server."""
        try:
            plex_server_url = await self.config.plex_server_url()
            plex_server_auth_token = await self.config.plex_server_auth_token()

            loop = ctx.bot.loop
            self.plex = await loop.run_in_executor(None, lambda: PlexServer(plex_server_url, plex_server_auth_token))

            await ctx.send("Connection to Plex server was successful.")
        except Exception as e:
            await ctx.send(f"Failed to connect to Plex server: ```{e}```")
            
    @bestof.command(name="poster")
    async def set_poster(self, ctx, url: str):
        """Sets the poster URL for the created Plex collection."""
        self.poster_url = url
        await ctx.send(f"Poster URL set to: {url}")

    @bestof.command(name="description")
    async def set_description(self, ctx, *, description: str):
        """Sets the description for the created Plex collection."""
        self.description = description
        await ctx.send("Description set.")

    @bestof.command(name="libraries")
    async def set_libraries(self, ctx: commands.Context):
        """Sets the allowed libraries to vote in."""
        libraries = self.plex.library.sections()
        allowed_libraries = [lib for lib in libraries if lib.type in {"movie", "show"}]

        # Send an embed with the list of libraries and their numbers
        library_list = "\n".join(f"{idx + 1}. {lib.title}" for idx, lib in enumerate(allowed_libraries))
        embed = discord.Embed(title="Available Libraries", description=library_list, color=discord.Color.green())
        message = await ctx.send(embed=embed)

        # Request the user to input the library numbers
        await ctx.send("Please type the numbers of the libraries you want to allow, separated by spaces (e.g. '1 2 3 4 7'):")

        # Check if the message author is the same as the command author and if the content contains valid numbers
        def check(msg):
            if msg.author != ctx.author:
                return False
            numbers = msg.content.split()
            return all(num.isdigit() and 1 <= int(num) <= len(allowed_libraries) for num in numbers)

        user_response = await self.bot.wait_for("message", check=check, timeout=60)

        # Update the allowed libraries configuration
        selected_library_numbers = [int(num) for num in user_response.content.split()]
        allowed_libraries_config = [allowed_libraries[i - 1].title for i in selected_library_numbers]
        await self.config.allowed_libraries.set(allowed_libraries_config)

        await ctx.send(f"Allowed libraries updated: {', '.join(allowed_libraries_config)}")
        
    @bestof.command(name='reset')
    @commands.has_guild_permissions(administrator=True)
    async def reset_config(self, ctx):
        """Reset the cog configuration for this server."""
        await self.config.guild(ctx.guild).clear()
        await ctx.send("Cog configuration has been reset for this server.")
        
    @bestof.command(name="config")
    @commands.is_owner()
    async def show_config(self, ctx):
        """Shows the current configuration of the BestOf cog."""
        plex_server_url = await self.config.plex_server_url()
        plex_server_auth_token = await self.config.plex_server_auth_token()  # Not displaying the token for security reasons
        allowed_libraries = await self.config.allowed_libraries()
        default_color = await ctx.embed_color()

        embed = discord.Embed(title="BestOf Configuration", color=default_color)

        embed.add_field(name="Plex Server URL", value=plex_server_url or "Not Set", inline=False)
        embed.add_field(name="Plex Server Authentication Token", value="Hidden for security" or "Not Set", inline=False)
        embed.add_field(name="Allowed Libraries", value=", ".join(allowed_libraries) if allowed_libraries else "None", inline=False)

        await ctx.send(embed=embed)

    @commands.command()
    async def vote(self, ctx):
        allowed_libraries = await self.config.allowed_libraries()

        if not allowed_libraries:
            await ctx.send("No libraries have been configured for voting.")
            return

        select_menu = LibrarySelect(allowed_libraries, self)
        view = View()
        view.add_item(select_menu)

        await ctx.send("Select a Library to Vote In", view=view)

    async def add_vote(self, interaction, library_name: str, title: str, is_tv_show: bool = False):
        # Ensure the Plex server has been initialized
        if not self.plex:
            await interaction.followup.send("The Plex server has not been configured.", ephemeral=True)
            return

        # Find the library with the given name
        try:
            libraries = self.plex.library.sections()
        except Exception as e:
            await interaction.followup.send("Failed to retrieve libraries from Plex server.")
            return  # Early return on error

        library = next((lib for lib in libraries if lib.title == library_name), None)
        if not library:
            await interaction.followup.send("Library not found.")
            return

        try:
            if is_tv_show:
                item = next((show for show in library.search(title) if show.type == 'show'), None)
            else:
                item = next((movie for movie in library.search(title) if movie.type == 'movie'), None)
        except Exception as e:
            await interaction.followup.send("Failed to search for the title in Plex library.")
            return  # Early return on error

        if not item:
            await interaction.followup.send("Item not found.")
            return
        
        item_key = item.key
        item_year = item.year if item.year else "Unknown Year"

        # Get current year
        current_year = datetime.now().year
        
        if item.year is None or item.year >= current_year:
            await interaction.followup.send(f"You can only vote for titles from previous years, not from {current_year}.", ephemeral=True)
            return

        # Confirm with the user that the correct item was found
        plex_web_url = f"https://app.plex.tv/web/index.html#!/server/{self.plex.machineIdentifier}/details?key={item.key}"
        poster_url = self.plex.url(item.thumb, includeToken=True) if item.thumb else None
        title_year = item.year if item.year else "Unknown Year"
        
        # Get the member's highest role with a non-default color
        member = interaction.user
        role_color = discord.Color.default()
        if isinstance(member, discord.Member):
            roles = sorted(member.roles, key=lambda r: r.position, reverse=True)
            for role in roles:
                if role.color.value != 0:  # Check if the role has a non-default color
                    role_color = role.color
                    break

        # Creating the embed
        embed = discord.Embed(
            title=item.title,
            url=plex_web_url,
            description=f"{item.summary}\n\n📌 **You will be voting for this title for the year {title_year}.**",
            color=role_color
        )

        # Add poster URL if available
        if poster_url:
            embed.set_thumbnail(url=poster_url)

        # Send a message mentioning the user along with the embed
        user_mention = interaction.user.mention  # Get the mention string for the user
        mention_message = f"{user_mention}, please confirm the title."
        
        # Send the embed and add reactions to the same message
        msg = await interaction.followup.send(content=mention_message, embed=embed)
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")

        # Reaction check
        def check(reaction, user):
            return user == interaction.user and reaction.message.id == msg.id and str(reaction.emoji) in ["✅", "❌"]

        try:
            reaction, _ = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
            if str(reaction.emoji) == "❌":
                await interaction.followup.send("Vote canceled. Make sure it's the exact same title on the Plex server.", ephemeral=True)
                return
        except asyncio.TimeoutError:
            await interaction.followup.send("No response received. Vote canceled.", ephemeral=True)
            return

        # Retrieve user's existing votes for the current year
        current_year = str(datetime.now().year)
        year_votes = user_votes.get(current_year, {})
        library_vote = year_votes.get(library_name, {})

        if library_vote:
            existing_title = library_vote.get('title')
            existing_year = library_vote.get('year')

            # Check if the user is trying to vote for the same title and year
            if existing_title == title and existing_year == item_year:
                # Send a confirmation message
                confirm_message = await interaction.followup.send(
                    f"You have already voted for '{existing_title}' in '{library_name}' for the year {item_year}. "
                    "Do you want to replace it? Respond with 'Yes' to replace or 'No' to cancel."
                )

                # Check for user response
                def check_confirm(m):
                    return m.author == interaction.user and m.channel == interaction.channel

                try:
                    confirm_response = await self.bot.wait_for("message", timeout=30.0, check=check_confirm)
                    if confirm_response.content.lower() != 'yes':
                        await interaction.followup.send("Vote not replaced.", ephemeral=True)
                        return
                except asyncio.TimeoutError:
                    await interaction.followup.send("Response timed out. Vote not replaced.", ephemeral=True)
                    return

        # Add or update the vote
        current_year = str(datetime.now().year)
        user_votes.setdefault(current_year, {}).setdefault(library_name, {})
        user_votes[current_year][library_name] = {'title': title, 'item_key': item_key, 'year': item_year}
        await self.config.user(interaction.user).votes.set(user_votes)

        await interaction.followup.send(f"Vote for `{title}` ({item_year}) recorded.", ephemeral=True)

    async def get_top_titles(self):
        # Get data for all users who voted
        user_data = await self.config.all_users()
        votes = self.process_votes(user_data)

        # Get the most voted title for each library and year
        top_titles = {}
        for year, libraries in votes.items():
            top_titles[year] = {}
            for library_name, titles in libraries.items():
                top_title = max(titles, key=titles.get)
                top_titles[year][library_name] = top_title

        return top_titles

    async def get_collection(self, library, collection_title):
        """Returns a Plex collection with the given title if it exists, else None."""
        for collection in library.collections():
            if collection.title == collection_title:
                return collection
        return None

    @commands.command()
    async def topvotes(self, ctx, specified_year: Optional[int] = None):
        current_year = datetime.today().year
        year = specified_year if specified_year and specified_year < current_year else current_year - 1

        user_data = await self.config.all_users()
        votes = self.process_votes(user_data)

        # Extract all years that have votes
        all_years = {vote_info.get('year') for _, user_votes in user_data.items() for vote_info in user_votes.get('votes', {}).values()}

        embed, data_exists = await self.create_topvotes_embed(votes, year, ctx, all_years)
        if not data_exists:
            await ctx.send(embed=embed)
            return

        message = await ctx.send(embed=embed)

        # Add navigation reactions if applicable
        if data_exists['previous']:
            await message.add_reaction('⬅️')
        if data_exists['next']:
            await message.add_reaction('➡️')

        # Reaction check
        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ['⬅️', '➡️'] and reaction.message.id == message.id

        # Reaction listener
        while True:
            try:
                reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
                if str(reaction.emoji) == '⬅️' and data_exists['previous']:
                    year -= 1
                elif str(reaction.emoji) == '➡️' and data_exists['next']:
                    year += 1

                embed, data_exists = await self.create_topvotes_embed(votes, year, ctx, all_years)
                await message.edit(embed=embed)

                # Update reactions
                if data_exists['previous']:
                    await message.add_reaction('⬅️')
                else:
                    await message.clear_reaction('⬅️')

                if data_exists['next']:
                    await message.add_reaction('➡️')
                else:
                    await message.clear_reaction('➡️')

                await message.remove_reaction(reaction.emoji, user)

            except asyncio.TimeoutError:
                break
        
    @commands.command()
    async def topvotes(self, ctx, specified_year: Optional[int] = None):
        current_year = datetime.today().year
        year = specified_year if specified_year and specified_year < current_year else current_year - 1

        user_data = await self.config.all_users()
        votes = self.process_votes(user_data)

        # Extract all years that have votes
        all_years = {vote_info.get('year') for _, user_votes in user_data.items() for vote_info in user_votes.get('votes', {}).values()}

        embed, data_exists = await self.create_topvotes_embed(votes, year, ctx, all_years)
        if not data_exists:
            await ctx.send(embed=embed)
            return

        message = await ctx.send(embed=embed)

        # Add navigation reactions if applicable
        if data_exists['previous']:
            await message.add_reaction('⬅️')
        if data_exists['next']:
            await message.add_reaction('➡️')

        # Reaction check
        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ['⬅️', '➡️'] and reaction.message.id == message.id

        # Reaction listener
        while True:
            try:
                reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
                if str(reaction.emoji) == '⬅️' and data_exists['previous']:
                    year -= 1
                elif str(reaction.emoji) == '➡️' and data_exists['next']:
                    year += 1

                embed, data_exists = await self.create_topvotes_embed(votes, year, ctx, all_years)
                await message.edit(embed=embed)

                # Update reactions
                if data_exists['previous']:
                    await message.add_reaction('⬅️')
                else:
                    await message.clear_reaction('⬅️')

                if data_exists['next']:
                    await message.add_reaction('➡️')
                else:
                    await message.clear_reaction('➡️')

                await message.remove_reaction(reaction.emoji, user)

            except asyncio.TimeoutError:
                break
        
    async def create_topvotes_embed(self, votes, year, ctx, all_years):
        default_color = await ctx.embed_color()
        server_name = ctx.guild.name
        embed = discord.Embed(title=f"{server_name}'s Best of {year}", color=default_color or discord.Color.default())
        
        allowed_libraries = await self.config.allowed_libraries()

        min_year = min(all_years, default=datetime.today().year - 1)
        max_year = max(all_years, default=datetime.today().year - 1)

        data_exists = {
            'previous': year > min_year,
            'next': year < max_year and year < datetime.today().year - 1
        }

        for library_name in allowed_libraries:
            library_votes = votes.get(library_name, {})
            for (title, vote_year, key), count in library_votes.items():
                if vote_year == year:
                    plex_web_url = f"https://app.plex.tv/web/index.html#!/server/{self.plex.machineIdentifier}/details?key={key}"
                    embed.add_field(
                        name=f"**{library_name}**",
                        value=f"[{title}]({plex_web_url}) - Votes: {count}",
                        inline=True
                    )

        if not embed.fields:
            embed.description = "No votes have been registered for this year."

        return embed, data_exists

    def process_votes(self, user_data):
        votes = {}
        for user_id, user_votes in user_data.items():
            for year, libraries in user_votes.get('votes', {}).items():
                for library_name, vote_info in libraries.items():
                    title = vote_info.get('title')
                    item_key = vote_info.get('item_key')
                    if title and item_key:
                        votes.setdefault(year, {}).setdefault(library_name, {}).setdefault((title, item_key), 0)
                        votes[year][library_name][(title, item_key)] += 1
        return votes

    @bestof.command(name='createcollection')
    @commands.has_guild_permissions(administrator=True)
    async def createcollection(self, ctx):
        """Create the Plex collection."""
        # Get the most voted titles
        top_titles = await self.get_top_titles()

        # Create a collection for each library and add the most voted title
        for library_name, top_title in top_titles.items():
            library = self.plex.library.section(library_name)
            server_name = self.plex.friendlyName
            collection_title = f"Best of {server_name}"
            collection = await self.get_collection(library, collection_title)
            if not collection:
                collection = library.createCollection(
                    collection_title,
                    smart=False,
                    summary=self.description,
                    **({'poster': self.poster_url} if self.poster_url else {})
                )
            else:
                collection.edit(
                    summary=self.description,
                    **({'poster': self.poster_url} if self.poster_url else {})
                )

            title = library.search(top_title)[0]
            collection.addItems(title)

        await ctx.send("Collections created.")
        
class LibrarySelect(Select):
    def __init__(self, libraries, cog, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.libraries = libraries
        self.cog = cog
        for library_name in libraries:
            self.add_option(label=library_name)

    async def callback(self, interaction: discord.Interaction):
        selected_library = self.values[0]
        if not self.cog.plex:
            await interaction.response.send_message("The Plex server has not been configured.", ephemeral=True)
            return

        library = self.cog.plex.library.section(selected_library)
        is_tv_show = library.type == "show"

        await interaction.response.send_message(f"Selected library: **{selected_library}**. Please type the title you want to vote for. **It must be the exact title on Plex.**")

        def message_check(m):
            return m.author == interaction.user and m.channel == interaction.channel

        try:
            title_message = await self.cog.bot.wait_for("message", timeout=60.0, check=message_check)
            title = title_message.content
            await self.cog.add_vote(interaction, selected_library, title, is_tv_show=is_tv_show)
        except asyncio.TimeoutError:
            await interaction.followup.send("No response received. Vote canceled.", ephemeral=True)
