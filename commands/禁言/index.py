import discord
from discord import app_commands
from discord.ext import commands
import datetime

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="mute", description="【🔨管理員專用】 對指定成員進行暫時禁言")
    @app_commands.guild_only()
    @app_commands.describe(
        member="選擇要禁言的成員",
        duration="選擇禁言時長",
        reason="輸入禁言原因"
    )
    @app_commands.choices(duration=[
        app_commands.Choice(name="10 分鐘", value=10),
        app_commands.Choice(name="1 小時", value=60),
        app_commands.Choice(name="1 天", value=1440),
        app_commands.Choice(name="7 天", value=10080),
        app_commands.Choice(name="30 天", value=43200),
    ])
    async def timeout_user(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        duration: app_commands.Choice[int],
        reason: str = "無提供"
    ):
        if not interaction.user.guild_permissions.moderate_members and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("你沒有權限使用此禁言指令！", ephemeral=True)
            return

        if member.top_role >= interaction.user.top_role and interaction.guild.owner_id != interaction.user.id:
            await interaction.response.send_message("無法禁言職位高於或平於你的成員！", ephemeral=True)
            return

        minutes = duration.value
        until_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=minutes)

        try:
            await member.timeout(until_time, reason=reason)
            embed = discord.Embed(title="🚫 成員禁言成功", color=discord.Color.red())
            embed.add_field(name="被禁言人", value=member.mention, inline=True)
            embed.add_field(name="執行管理員", value=interaction.user.mention, inline=True)
            embed.add_field(name="禁言時長", value=duration.name, inline=True)
            embed.add_field(name="禁言原因", value=reason, inline=False)
            embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
            
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            await interaction.response.send_message(f"❌ 執行禁言時發生錯誤：{e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Moderation(bot))