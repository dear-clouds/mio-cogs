import discord
import plexapi
import asyncio
from redbot.core import commands, Config, app_commands
from discord.ui import View, Select
from plexapi.server import PlexServer
from datetime import datetime
from typing import Optional
import random
import requests
import logging

class BestOf(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=199523456789)
        self.config.register_global(
            plex_server_url=None,
            plex_server_auth_token=None,
            tautulli_url=None,
            tautulli_api=None,
            allowed_libraries=[],
            description=None,
            poster=None
        )
        self.config.register_user(votes={})
        self.plex = None
        self.description = None
        self.poster_url = None

    async def cog_load(self):
        await self.initialize()

    async def initialize(self):
        await self.bot.wait_until_ready()
        plex_server_url = await self.config.plex_server_url()
        plex_server_auth_token = await self.config.plex_server_auth_token()
        self.description = await self.config.description()
        self.poster_url = await self.config.poster()
        
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
        
    @bestof.command(name="tautulliurl")
    async def set_tautulliurl(self, ctx, url: str):
        """Sets the Tautulli URL."""
        await self.config.tautulli_url.set(url)
        await ctx.send(f"Tautulli URL set to `{url}`.")

    @bestof.command(name="tautulliapi")
    async def set_tautulliapi(self, ctx, key: str):
        """Sets the Tautulli Api Key."""
        await self.config.tautulli_api.set(key)
        await ctx.send(f"Tautulli Api Key set to `{key}`.")
        
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
            
    @bestof.command(name="tmdb")
    async def set_tmdb(self, ctx, key: str):
        """Sets the TMDB Api Key."""
        await self.config.tmdb_key.set(key)
        await ctx.send(f"TMDB Api Key set to `{key}`.")
            
    @bestof.command(name="poster")
    async def set_poster(self, ctx, url: str):
        """Sets the poster URL for the created Plex collection."""
        await self.config.poster.set(url)
        await ctx.send(f"Poster URL set to: {url}")

    @bestof.command(name="description")
    async def set_description(self, ctx, *, description: str):
        """Sets the description for the created Plex collection."""
        await self.config.description.set(description)
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

        await ctx.send("Select a Library to Vote In. **You can only vote for one title per library and per year.**", view=view)

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
        item_title = item.title
        item_year = item.year if item.year else "Unknown Year"
        poster_url = await self.fetch_image_from_tautulli(item_key)

        # Get current year
        current_year = datetime.now().year
        
        if item.year is None or item.year >= current_year:
            await interaction.followup.send(f"You can only vote for titles from previous years, not from {current_year}.", ephemeral=True)
            return

        # Confirm with the user that the correct item was found
        plex_web_url = f"https://app.plex.tv/web/index.html#!/server/{self.plex.machineIdentifier}/details?key={item.key}"
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
            embed.set_image(url=poster_url)

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
        
        # Retrieve the current votes for the user
        user_votes = await self.config.user(interaction.user).votes()
        
        # Use the title's release year as the key
        year_str = str(item_year)
        year_votes = user_votes.get(year_str, {})
        library_vote = year_votes.get(library_name, {})

        if library_vote:
            existing_title = library_vote.get('title')
            if existing_title:
                # Send a confirmation message
                confirm_message = await interaction.followup.send(
                    f"You have already voted for **{existing_title}** in **{library_name}** for the year **{item_year}**. "
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
        year_votes[library_name] = {'title': item_title, 'item_key': item_key}
        user_votes[year_str] = year_votes
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
        
    @commands.hybrid_command(name="topvotes", description="Show top voted titles")
    async def topvotes(self, ctx_or_interaction, specified_year: Optional[int] = None):
        current_year = datetime.today().year
        year = specified_year if specified_year and specified_year < current_year else current_year - 1

        user_data = await self.config.all_users()
        votes = self.process_votes(user_data)

        # Extract all years that have votes
        all_years = set()
        for _, user_votes in user_data.items():
            for year_str in user_votes.get('votes', {}):
                try:
                    all_years.add(int(year_str))
                except ValueError:
                    continue

        if not all_years:
            await ctx_or_interaction.send("No votes have been registered.")
            return

        embed, data_exists = await self.create_topvotes_embed(votes, year, ctx_or_interaction, all_years)

        # Check if it's an interaction or a context and send the message accordingly
        if isinstance(ctx_or_interaction, commands.Context):
            message = await ctx_or_interaction.send(embed=embed)
            author = ctx_or_interaction.author
        elif isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.response.send_message(embed=embed)
            message = await ctx_or_interaction.original_message()
            author = ctx_or_interaction.user
        else:
            return  # In case it's neither

        # Add navigation reactions if applicable
        if year > min(all_years):
            await message.add_reaction('⬅️')
        if year < max(all_years):
            await message.add_reaction('➡️')

        # Reaction check
        def check(reaction, user):
            return user == author and str(reaction.emoji) in ['⬅️', '➡️'] and reaction.message.id == message.id

        # Reaction listener
        while True:
            try:
                reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
                if str(reaction.emoji) == '⬅️' and data_exists['previous']:
                    year -= 1
                elif str(reaction.emoji) == '➡️' and data_exists['next']:
                    year += 1

                embed, data_exists = await self.create_topvotes_embed(votes, year, ctx_or_interaction, all_years)
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
        
    async def create_topvotes_embed(self, votes, year, ctx_or_interaction, all_years):
        # Define guild variable at the beginning
        if isinstance(ctx_or_interaction, commands.Context):
            guild = ctx_or_interaction.guild
            default_color = await ctx_or_interaction.embed_color()
        elif isinstance(ctx_or_interaction, discord.Interaction):
            guild = ctx_or_interaction.guild
            default_color = guild.me.color if guild else discord.Color.default()
        else:
            guild = None
            default_color = discord.Color.default()

        server_name = guild.name if guild else "Unknown Server"
        embed = discord.Embed(title=f"🏆 {server_name}'s Best of {year}", color=default_color)

        allowed_libraries = await self.config.allowed_libraries()

        year_str = str(year)
        
        # Dictionary to keep track of libraries already included
        included_libraries = {}

        for library_name in allowed_libraries:
            if year_str in votes and library_name in votes[year_str]:
                # Check if the library has already been included
                if library_name in included_libraries:
                    continue

                titles_combined = []  # List to combine titles from the same library

                for (title, item_key), count in votes[year_str][library_name].items():
                    plex_web_url = f"https://app.plex.tv/web/index.html#!/server/{self.plex.machineIdentifier}/details?key={item_key}"
                    titles_combined.append(f"[{title}]({plex_web_url}) - Votes: {count}")

                # Combine titles and add them to the embed
                titles_combined_text = "\n".join(titles_combined)
                embed.add_field(name=f"**{library_name}**", value=titles_combined_text, inline=True)

                # Mark the library as included
                included_libraries[library_name] = True

        if not embed.fields:
            embed.description = "No votes have been registered for this year."

        data_exists = {
            'previous': year > min(all_years),
            'next': year < max(all_years)
        }

        return embed, data_exists

    @bestof.command(name='createcollection')
    @commands.has_guild_permissions(administrator=True)
    async def createcollection(self, ctx):
        """Create a single Plex collection for the top voted titles of all years for each library."""
        allowed_libraries = await self.config.allowed_libraries()
        description = await self.config.description()
        poster_url = await self.config.poster()

        if not allowed_libraries:
            await ctx.send("No allowed libraries set. Please set the allowed libraries first.")
            return

        if not self.plex:
            await ctx.send("Plex server not configured properly.")
            return

        try:
            top_titles = await self.get_most_voted_titles()
            await ctx.send(f"Fetched most voted titles: {top_titles}")

            server_name = self.plex.friendlyName
            collection_title = f"{server_name}'s Awards"

            for library_name in allowed_libraries:
                await ctx.send(f"Processing library: {library_name}")
                try:
                    library = self.plex.library.section(library_name)
                    collection = await self.get_collection(library, collection_title)
                    if not collection:
                        await ctx.send(f"Creating new collection: {collection_title}")
                        collection = library.createCollection(
                            title=collection_title,
                            smart=False,
                            summary=description,
                            **({'poster': poster_url} if poster_url else {})
                        )
                        await ctx.send(f"Created new collection: {collection_title}")
                    else:
                        await ctx.send(f"Editing existing collection: {collection_title}")
                        collection.edit(
                            summary=description,
                            **({'poster': poster_url} if poster_url else {})
                        )
                        await ctx.send(f"Updated existing collection: {collection_title}")

                    if library_name in top_titles:
                        for title in top_titles[library_name]:
                            await ctx.send(f"Searching for title: {title}")
                            search_results = library.search(title)
                            if search_results:
                                await ctx.send(f"Adding title to collection: {title}")
                                collection.addItems(search_results[0])
                                await ctx.send(f"Added '{title}' to collection '{collection_title}'")
                            else:
                                await ctx.send(f"Title '{title}' not found in library '{library_name}'.")

                except Exception as e:
                    await ctx.send(f"Failed to process library '{library_name}': {e}")
                    print(f"Error creating collection for library '{library_name}': {e}")

            await ctx.send("All specified collections have been processed.")
        except Exception as e:
            await ctx.send(f"An error occurred while processing collections: {e}")
            print(f"Error in createcollection command: {e}")

    async def get_most_voted_titles(self):
        """Get the most voted titles for all years and libraries with at least 2 votes."""
        user_data = await self.config.all_users()
        votes = self.process_votes(user_data)
        top_titles = {}

        for year, libraries in votes.items():
            for library_name, titles in libraries.items():
                max_votes = 0
                top_title = None
                for (title, item_key), count in titles.items():
                    if count >= 2 and count > max_votes:
                        max_votes = count
                        top_title = title

                if top_title:
                    if library_name not in top_titles:
                        top_titles[library_name] = []
                    top_titles[library_name].append(top_title)

        return top_titles

    def process_votes(self, user_data):
        """Process user votes to determine the top titles."""
        votes = {}
        for user_id, years in user_data.items():
            for year, libraries in years.get('votes', {}).items():
                for library_name, vote_info in libraries.items():
                    if isinstance(vote_info, dict):
                        title = vote_info.get('title')
                        item_key = vote_info.get('item_key')
                        if title and item_key:
                            votes.setdefault(year, {}).setdefault(library_name, {}).setdefault((title, item_key), 0)
                            votes[year][library_name][(title, item_key)] += 1
        return votes

    async def get_collection(self, library, collection_title):
        """Returns a Plex collection with the given title if it exists, else None."""
        for collection in library.collections():
            if collection.title == collection_title:
                return collection
        return None
        
    @commands.command()
    async def favs(self, ctx, *, member: discord.Member = None):
        member = member or ctx.author
        user_votes = await self.config.user(member).votes()
        if not user_votes:
            await ctx.send(f"{member.display_name} hasn't voted for any titles yet.")
            return

        # Prepare lists for each category
        categories = {
            "Anime": [],
            "Variety Shows": [],
            "Dramas": [],
            "Movies": []
        }

        # Populate the lists
        for year, libraries in user_votes.items():
            for library_name, vote_info in libraries.items():
                if vote_info:
                    title = vote_info.get('title')
                    item_key = vote_info.get('item_key')
                    plex_web_url = f"https://app.plex.tv/web/index.html#!/server/{self.plex.machineIdentifier}/details?key={item_key}"
                    
                    try:
                        item = self.plex.fetchItem(item_key)
                        formatted_title = f"- [{title}]({plex_web_url})"
                        # Categorize the titles based on the library name and item type
                        if 'Anime' in library_name:
                            categories["Anime"].append(formatted_title)
                        elif 'Variety Show' in library_name:
                            categories["Variety Shows"].append(formatted_title)
                        elif item.type == 'movie':
                            categories["Movies"].append(formatted_title)
                        elif item.type == 'show':
                            categories["Dramas"].append(formatted_title)
                    except Exception as e:
                        continue  # Ignore errors and continue to the next item

        # Limit each category to 6 entries chosen randomly
        for category in categories.values():
            random.shuffle(category)
            if len(category) > 6:
                category[:] = category[:6]

        # Create a single embed for all titles
        embed = discord.Embed(title=f"❤️ {member.display_name}'s Favorites", color=member.top_role.color)
        embed.set_thumbnail(url=member.avatar.url)

        field_count = 0
        for category_name, title_list in categories.items():
            if title_list:
                embed.add_field(name=category_name, value="\n".join(title_list), inline=True)
                field_count += 1
                if field_count % 2 == 0:
                    embed.add_field(name='\u200b', value='\u200b', inline=True)  # Add a blank field for alignment

        # Random background image from one of the voted titles
        random_background_url = await self.get_random_background(user_votes)
        if random_background_url:
            embed.set_image(url=random_background_url)
        
        # Define the buttons and pass the cog instance
        vote_button = VoteButton(self)
        tops_button = TopsButton(self)

        # Create a View and add the buttons
        view = discord.ui.View()
        view.add_item(vote_button)
        view.add_item(tops_button)

        # Send the embed with the View
        await ctx.send(embed=embed, view=view)

    async def get_random_background(self, user_votes):
        # print("Entering get_random_background")
        backgrounds = []
        for year, libraries in user_votes.items():
            for library_name, vote_info in libraries.items():
                if vote_info:
                    item_key = vote_info.get('item_key')
                    try:
                        image_url = await self.fetch_image_from_tautulli(item_key)
                        if image_url:
                            backgrounds.append(image_url)
                    except Exception as e:
                        print(f"Error fetching image for item key {item_key} from Tautulli: {e}")
                        continue

        chosen_image = random.choice(backgrounds) if backgrounds else None
        # print(f"Chosen image URL: {chosen_image}")
        return chosen_image
    
    async def fetch_image_from_tautulli(self, item_key):
        tautulli_url = await self.config.tautulli_url()
        tautulli_api_key = await self.config.tautulli_api()

        # Extract the numeric ID from the item_key
        rating_key = item_key.split('/')[-1]

        params = {
            'apikey': tautulli_api_key,
            'cmd': 'get_metadata',
            'rating_key': rating_key
        }

        try:
            response = await self.bot.loop.run_in_executor(None, lambda: requests.get(f"{tautulli_url}/api/v2", params=params))
            if response.status_code == 200:
                data = response.json()
                # print(f"Tautulli API Response: {data}")
                if data['response']['result'] == 'success':
                    image_url = data['response']['data'].get('art') or data['response']['data'].get('thumb')
                    if image_url:
                        return f"{tautulli_url}/pms_image_proxy?img={image_url}.jpg"
            else:
                print(f"Error: Tautulli API responded with status code {response.status_code}")
        except Exception as e:
            print(f"Exception occurred while fetching image from Tautulli: {e}")

        return None

def paginate_titles(lists, titles_per_page=10):
    total_pages = max((len(lst) + titles_per_page - 1) // titles_per_page for lst in lists.values())
    pages = []

    for i in range(total_pages):
        page_content = {}
        for category, titles in lists.items():
            start_index = i * titles_per_page
            end_index = start_index + titles_per_page
            page_content[category] = titles[start_index:end_index]
        pages.append(page_content)
    return pages

class PaginatedView(discord.ui.View):
    def __init__(self, pages, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pages = pages
        self.current_page = 0
        self.add_item(PreviousButton())
        self.add_item(NextButton())

    async def update_embed(self, interaction: discord.Interaction):
        embed = self.create_embed_for_page(self.current_page)
        await interaction.response.edit_message(embed=embed)

    def create_embed_for_page(self, page_number):
        page = self.pages[page_number]
        embed = discord.Embed(title=f"❤️ {self.member.display_name}'s Favorites", color=self.role_color)
        
        for category, titles in page.items():
            if titles:
                embed.add_field(name=category, value="\n".join(titles), inline=True)

        embed.set_footer(text=f"Page {page_number + 1}/{len(self.pages)}")
        return embed
        
class LibrarySelect(Select):
    def __init__(self, libraries, cog, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.libraries = sorted(libraries)  # Sort the libraries alphabetically
        self.cog = cog
        for library_name in self.libraries:
            self.add_option(label=library_name)

    async def callback(self, interaction: discord.Interaction):
        selected_library = self.values[0]
        if not self.cog.plex:
            await interaction.response.send_message("The Plex server has not been configured.", ephemeral=True)
            return

        library = self.cog.plex.library.section(selected_library)
        is_tv_show = library.type == "show"

        await interaction.response.send_message(f"Selected library: **{selected_library}**. Please type the title you want to vote for. **It must be the exact title on Plex.**", ephemeral=True)

        def message_check(m):
            return m.author == interaction.user and m.channel == interaction.channel

        try:
            title_message = await self.cog.bot.wait_for("message", timeout=60.0, check=message_check)
            title = title_message.content
            await self.cog.add_vote(interaction, selected_library, title, is_tv_show=is_tv_show)
        except asyncio.TimeoutError:
            await interaction.followup.send("No response received. Vote canceled.", ephemeral=True)

class VoteButton(discord.ui.Button):
    def __init__(self, cog, *args, **kwargs):
        super().__init__(*args, **kwargs, label="Vote", emoji="🗳️", style=discord.ButtonStyle.grey)
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()  # Acknowledge the interaction
        ctx = await self.cog.bot.get_context(interaction.message)
        await ctx.invoke(self.cog.vote)

class TopsButton(discord.ui.Button):
    def __init__(self, cog, *args, **kwargs):
        super().__init__(*args, **kwargs, label="Tops", emoji="🏆", style=discord.ButtonStyle.primary)
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        # Invoke the hybrid command directly with the interaction
        await self.cog.topvotes(interaction, None)
        
class NextButton(discord.ui.Button):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs, label="Next", style=discord.ButtonStyle.green)

    async def callback(self, interaction: discord.Interaction):
        self.view.current_page += 1
        await self.view.update_embed(interaction)

class PreviousButton(discord.ui.Button):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs, label="Previous", style=discord.ButtonStyle.green)

    async def callback(self, interaction: discord.Interaction):
        self.view.current_page -= 1
        await self.view.update_embed(interaction)
