import discord
import plexapi
import asyncio
import aiohttp
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
            allowed_libraries=[],
            voting_month=1
        )
        self.config.register_user(votes={})
        self.plex = None

    async def initialize(self):
        await self.bot.wait_until_ready()
        plex_server_url = await self.config.plex_server_url()
        plex_server_auth_token = await self.config.plex_server_auth_token()
        self.plex = PlexServer(plex_server_url, plex_server_auth_token)

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

    @bestof.command(name="votingmonth")
    async def set_votingmonth(self, ctx, month: int):
        """Sets the month when the voting is allowed."""
        if 1 <= month <= 12:
            await self.config.voting_month.set(month)
            await ctx.send(f"Voting month updated to {month}.")
        else:
            await ctx.send("Invalid month. Please enter a value between 1 and 12.")
            
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
        voting_month = await self.config.voting_month()
        current_month = datetime.today().month
        if current_month != voting_month:
            await interaction.response.send_message(f"Voting is only allowed during month {voting_month}.", ephemeral=True)
            return

        # Ensure the Plex server has been initialized
        if not self.plex:
            await interaction.followup.send("The Plex server has not been configured.", ephemeral=True)
            return

        # Find the library with the given name
        libraries = self.plex.library.sections()
        library = None
        for lib in libraries:
            if lib.title == library_name:
                library = lib
                break
        if not library:
            await interaction.followup.send("Library not found.", ephemeral=True)
            return

        # Find the item with the given title
        item = None
        if is_tv_show:
            for show in library.search(title):
                if show.type == 'show':
                    item = show
                    break
        else:
            for movie in library.search(title):
                if movie.type == 'movie':
                    item = movie
                    break
        if not item:
            await interaction.followup.send("Item not found.", ephemeral=True)
            return

        # Confirm with the user that the correct item was found
        # Generate Plex Web URL for the title
        plex_web_url = f"https://app.plex.tv/web/index.html#!/server/{self.plex.machineIdentifier}/details?key={item.key}"

        # Generate Poster URL
        poster_url = self.plex.url(item.thumb, includeToken=True) if item.thumb else None

        # Confirm with the user that the correct item was found
        embed = discord.Embed(
            title=item.title,
            url=plex_web_url,
            description=item.summary
        )

        # Add poster URL if available
        if poster_url:
            embed.set_image(url=poster_url)

        msg = await interaction.followup.send(embed=embed)
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")

        def check(reaction, user):
            return user == interaction.user and reaction.message.id == msg.id and str(reaction.emoji) in ["✅", "❌"]

        try:
            reaction, _ = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
            if str(reaction.emoji) == "❌":
                await interaction.followup.send("Vote canceled.", ephemeral=True)
                return
        except asyncio.TimeoutError:
            await interaction.followup.send("No response received. Vote canceled.", ephemeral=True)
            return

        # Check if the user has already voted for the given title in the given library
        user_votes = await self.config.user(interaction.user).votes()
        if library_name not in user_votes:
            user_votes[library_name] = {}

        if title in user_votes[library_name]:
            await interaction.followup.send("You have already voted for a title in this library.", ephemeral=True)
            return

        # Add the vote to the user's data
        user_votes[library_name][title] = item.rating
        await self.config.user(interaction.user).votes.set(user_votes)

        await interaction.followup.send(f"Vote for `{item.title}` recorded.", ephemeral=True)

    async def get_top_movies(self):
        # Get data for all users who voted during January
        user_data = await self.config.all_users()
        votes = {}
        for uid, data in user_data.items():
            if 'votes' in data:
                for library_name, movies in data['votes'].items():
                    for title, rating in movies.items():
                        if library_name not in votes:
                            votes[library_name] = {}
                        if title not in votes[library_name]:
                            votes[library_name][title] = 0
                        votes[library_name][title] += 1

        # Get the most voted title for each library
        top_movies = {}
        for library_name, movies in votes.items():
            top_movie = max(movies, key=movies.get)
            top_movies[library_name] = top_movie

        return top_movies

    async def get_collection(self, library, collection_title):
        """Returns a Plex collection with the given title if it exists, else None."""
        for collection in library.collections():
            if collection.title == collection_title:
                return collection
        return None

    @commands.command()
    async def topvotes(self, ctx, years: int = 1):
        """Shows the top titles for the past years. Defaults to 1 year."""
        if years < 1:
            await ctx.send("Please enter a positive integer for the number of years.")
            return

        # Get data for all users who voted in the past years
        user_data = await self.config.all_users()
        votes = {}
        for uid, data in user_data.items():
            if 'votes' in data:
                for library_name, movies in data['votes'].items():
                    for title, rating in movies.items():
                        if library_name not in votes:
                            votes[library_name] = {}
                        date_voted = datetime.strptime(
                            data['last_vote'], '%Y-%m-%d %H:%M:%S.%f')
                        if date_voted.year >= datetime.today().year - years:
                            if title not in votes[library_name]:
                                votes[library_name][title] = []
                            votes[library_name][title].append(rating)

        # Calculate the average rating for each title in each library
        avg_ratings = {}
        for library_name, movies in votes.items():
            for title, ratings in movies.items():
                if library_name not in avg_ratings:
                    avg_ratings[library_name] = {}
                avg_ratings[library_name][title] = sum(ratings) / len(ratings)

        # Sort the titles by average rating and return the top 3 for each library
        top_movies = {}
        for library_name, movies in avg_ratings.items():
            top_movies[library_name] = sorted(
                movies, key=movies.get, reverse=True)[:3]

        # Create and send an embed with the top titles for each library
        current_year = datetime.today().year
        embed = discord.Embed(
            title=f"Top Titles for {current_year - years + 1} - {current_year}", color=discord.Color.blurple())
        for library_name, movies in top_movies.items():
            library = self.plex.library.section(library_name)
            movie_str = ""
            for movie_title in movies:
                movie = library.get(movie_title)
                movie_str += f"\n[{movie_title}]({movie.guid}): {avg_ratings[library_name][movie_title]:.1f}"
            if movie_str:
                embed.add_field(name=library_name,
                                value=movie_str, inline=False)

        await ctx.send(embed=embed)

    @commands.command()
    @commands.is_owner()
    async def createcollection(self, ctx):
        """Create the Plex collection."""
        # Get the most voted titles
        top_movies = await self.get_top_movies()

        # Create a collection for each library and add the most voted title
        for library_name, top_movie_title in top_movies.items():
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

            movie = library.search(top_movie_title)[0]
            collection.addItems(movie)

        await ctx.send("Collections created.")
        
class LibrarySelect(Select):
    def __init__(self, libraries, cog, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.libraries = libraries
        self.cog = cog
        for library_name in libraries:
            self.add_option(label=library_name)

    async def callback(self, interaction: discord.Interaction):
        # Get the selected library name
        selected_library = self.values[0]

        # Ensure the Plex server has been initialized
        if not self.cog.plex:
            await interaction.response.send_message("The Plex server has not been configured.", ephemeral=True)
            return

        # Get the library object from the Plex server
        library = self.cog.plex.library.section(selected_library)
        is_tv_show = library.type == "show"

        # Ask the user to type the title they want to vote for
        await interaction.response.send_message(f"Selected library: {selected_library}. Please type the title you want to vote for.")

        # Wait for the user's response
        def message_check(m):
            return m.author == interaction.user and m.channel == interaction.channel

        try:
            title_message = await self.cog.bot.wait_for("message", timeout=60.0, check=message_check)
        except asyncio.TimeoutError:
            await interaction.followup.send("No response received. Vote canceled.", ephemeral=True)
            return

        title = title_message.content
        await self.cog.add_vote(interaction, selected_library, title, is_tv_show=is_tv_show)
