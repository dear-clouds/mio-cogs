from .rewardrole import RewardRole

async def setup(bot):
    cog = RewardRole(bot)
    await bot.add_cog(cog)