import discord
import plexapi
import asyncio
from redbot.core import commands, Config
from plexapi.server import PlexServer
from datetime import datetime
from typing import Optional


class BestOf(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        self.config.register_global(
            plex_server_url=None,
            plex_server_auth_token=None,
            allowed_libraries=[]
        )
        self.config.register_user(votes={})
        self.plex = None
        self.current_month = datetime.today().month

    async def initialize(self):
        await self.bot.wait_until_ready()
        plex_server_url = await self.config.plex_server_url()
        plex_server_auth_token = await self.config.plex_server_auth_token()
        self.plex = PlexServer(plex_server_url, plex_server_auth_token)

    @commands.group(autohelp=True)
    @commands.guild_only()
    @commands.is_owner()
    async def setplex(self, ctx):
        """Plex server settings."""
        pass

    @setplex.command(name="url")
    async def setplex_url(self, ctx, url: str):
        """Sets the Plex server URL."""
        await self.config.plex_server_url.set(url)
        self.plex = PlexServer(url, await self.config.plex_server_auth_token())
        await ctx.send("Plex server URL updated.")

    @setplex.command(name="token")
    async def setplex_token(self, ctx, token: str):
        """Sets the Plex server authentication token."""
        await self.config.plex_server_auth_token.set(token)
        self.plex = PlexServer(await self.config.plex_server_url(), token)
        await ctx.send("Plex server authentication token updated.")

    @setplex.command(name="libraries")
    async def setplex_libraries(self, ctx: commands.Context):
        libraries = self.plex.library.sections()
        allowed_libraries = [lib for lib in libraries if lib.type in {"movie", "show"}]

        # Send a message with the list of libraries and their numbers
        library_list = "\n".join(f"{idx + 1}. {lib.title}" for idx, lib in enumerate(allowed_libraries))
        message = await ctx.send(f"Please choose a library by typing its number:\n{library_list}")

        # Check if the message author is the same as the command author and if the content is a valid number
        def check(msg):
            return (
                msg.author == ctx.author
                and msg.content.isdigit()
                and 1 <= int(msg.content) <= len(allowed_libraries)
            )

        try:
            user_response = await self.bot.wait_for("message", check=check, timeout=60)
        except asyncio.TimeoutError:
            await ctx.send("Time's up! Please try again.")
            return

        selected_library = allowed_libraries[int(user_response.content) - 1]
        selected_library = libraries[index].title
        allowed_libraries = await self.config.allowed_libraries()
        allowed_libraries.append(selected_library)
        await self.config.allowed_libraries.set(allowed_libraries)

        await ctx.send(f"Allowed library updated: {selected_library}")

    @commands.command()
    async def vote(self, ctx):
        """Vote for the titles you think were the best this year! Only 1 title per library."""
        allowed_libraries = await self.config.allowed_libraries()

        if not allowed_libraries:
            await ctx.send("No libraries have been configured for voting.")
            return

        embed = discord.Embed(title="Select a Library to Vote In", color=discord.Color.blue())
        for idx, library_name in enumerate(allowed_libraries):
            embed.add_field(name=f"{idx + 1}. {library_name}", value="\u200b", inline=False)

        message = await ctx.send(embed=embed)
        for idx in range(len(allowed_libraries)):
            await message.add_reaction(f"{idx + 1}\N{combining enclosing keycap}")

        def check(reaction, user):
            return (
                user == ctx.author
                and reaction.message.id == message.id
                and reaction.emoji in [f"{i + 1}\N{combining enclosing keycap}" for i in range(len(allowed_libraries))]
            )

        try:
            reaction, _ = await self.bot.wait_for("reaction_add", timeout=60.0, check=check)
        except asyncio.TimeoutError:
            await ctx.send("No response received. Vote canceled.")
            return

        index = int(reaction.emoji[0]) - 1
        selected_library = allowed_libraries[index]

        await ctx.send(f"Selected library: {selected_library}. Please type the title you want to vote for.")
        def message_check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            title_message = await self.bot.wait_for("message", timeout=60.0, check=message_check)
        except asyncio.TimeoutError:
            await ctx.send("No response received. Vote canceled.")
            return

        title = title_message.content
        await self.add_vote(ctx, selected_library, title)

    async def add_vote(self, ctx, library_name: str, title: str, is_tv_show: bool = False):
        if self.current_month != 1:
            await ctx.send("Voting is only allowed during January.")
            return

        # Ensure the Plex server has been initialized
        if not self.plex:
            await ctx.send("The Plex server has not been configured.")
            return

        # Find the library with the given name
        libraries = self.plex.library.sections()
        library = None
        for lib in libraries:
            if lib.title == library_name:
                library = lib
                break
        if not library:
            await ctx.send("Library not found.")
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
            await ctx.send("Item not found.")
            return

        # Confirm with the user that the correct item was found
        embed = discord.Embed(
            title=item.title,
            url=item.guid,
            description=item.summary
        )
        embed.set_image(url=item.thumb)
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")

        def check(reaction, user):
            return user == ctx.author and reaction.message.id == msg.id and str(reaction.emoji) in ["✅", "❌"]

        try:
            reaction, _ = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
            if str(reaction.emoji) == "❌":
                await ctx.send("Vote canceled.")
                return
        except asyncio.TimeoutError:
            await ctx.send("No response received. Vote canceled.")
            return

        # Check if the user has already voted for the given title in the given library
        user_votes = await self.config.user(ctx.author).votes()
        if library_name not in user_votes:
            user_votes[library_name] = {}

        if title in user_votes[library_name]:
            await ctx.send("You have already voted for a title in this library.")
            return

        # Add the vote to the user's data
        user_votes[library_name][title] = item.rating
        await self.config.user(ctx.author).votes.set(user_votes)

        await ctx.send(f"Vote for `{item.title}` recorded.")

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
        embed = discord.Embed(
            title=f"Top Titles for the Past {years} Years", color=discord.Color.blurple())
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
    async def create_collection(self, ctx):
        """Create the Plex collection."""
        if self.current_month != 2:
            await ctx.send("This command can only be run during February.")
            return

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

    @commands.command()
    async def vote(self, ctx, library_name: str, title: str):
        """Vote for the titles you think were the best this year! Only 1 title per library."""
        await self.add_vote(ctx, library_name, title)

    @commands.command()
    @commands.is_owner()
    async def setposter(self, ctx, url: str):
        """Sets the poster URL for the created Plex collection."""
        self.poster_url = url
        await ctx.send(f"Poster URL set to: {url}")

    @commands.command()
    @commands.is_owner()
    async def setdescription(self, ctx, *, description: str):
        """Sets the description for the created Plex collection."""
        self.description = description
        await ctx.send("Description set.")
