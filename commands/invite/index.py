import discord
from discord import app_commands
from discord.ext import commands


class Invite(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="invite", description="取得邀請機器人加入其他伺服器的連結")
    async def invite(self, interaction: discord.Interaction):
        application_id = self.bot.application_id
        if application_id is None:
            await interaction.response.send_message(
                "機器人 Application ID 尚未準備完成，請稍後再試。",
                ephemeral=True,
            )
            return

        invite_url = discord.utils.oauth_url(
            application_id,
            permissions=discord.Permissions.none(),
            scopes=("bot", "applications.commands"),
        )
        embed = discord.Embed(
            title="🤖 邀請機器人",
            description=(
                f"[點此邀請機器人加入你的伺服器]({invite_url})\n\n"
                "請使用目標伺服器的管理員帳號開啟連結。"
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="加入後",
            value="請在新伺服器執行 `/設定伺服器`、`/setup` 與 `/設定付款`。",
            inline=False,
        )
        embed.set_footer(text="需要協助請聯繫管理員")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Invite(bot))
