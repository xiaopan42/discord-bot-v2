import datetime

import discord
from discord import app_commands
from discord.ext import commands

import database
from commands.shared.formatters import format_price


class SpendingAdjustment(commands.Cog):
    @app_commands.command(name="調整消費", description="【🔨管理員專用】 手動加減老闆的消費金額")
    @app_commands.guild_only()
    @app_commands.describe(member="請選擇要調整金額的老闆", amount="正數增加、負數減少", reason="調整原因或備註")
    async def adjust_spending(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        amount: float,
        reason: str = "管理員手動調整",
    ):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("你沒有權限使用此指令！", ephemeral=True)
            return

        database.add_spending_adjustment(
            interaction.guild_id, member.id, amount, reason, interaction.user.id
        )
        spending = database.get_user_spending(interaction.guild_id, member.id)
        sign = "+" if amount >= 0 else ""
        embed = discord.Embed(
            title="✅ 消費金額手動調整完成",
            color=discord.Color.green() if amount >= 0 else discord.Color.red(),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.add_field(name="老闆名稱", value=member.mention, inline=True)
        embed.add_field(name="執行管理員", value=interaction.user.mention, inline=True)
        embed.add_field(name="本次調整金額", value=f"**`{sign}{format_price(amount)}`**", inline=False)
        embed.add_field(name="調整原因", value=f"`{reason}`", inline=False)
        embed.add_field(name="更新後總累積消費", value=f"**`{format_price(spending['total_spending'])}`**", inline=True)
        embed.add_field(name="更新後當月消費", value=f"**`{format_price(spending['monthly_spending'])}`**", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(SpendingAdjustment(bot))
