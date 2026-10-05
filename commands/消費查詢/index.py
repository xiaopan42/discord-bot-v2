import discord
from discord import app_commands
from discord.ext import commands
import database
import datetime

from commands.shared.formatters import format_price

class Spending(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="查詢消費", description="💰 查詢老闆的總累積消費與當月消費")
    @app_commands.guild_only()
    @app_commands.describe(
        member="選擇要查詢的老闆（可選，非管理員預設為自己）"
    )
    async def query_spending(
        self,
        interaction: discord.Interaction,
        member: discord.Member = None
    ):
        target_member = member or interaction.user
        
        # 如果查詢其他人，限制僅管理員可查詢
        if member and member.id != interaction.user.id:
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("你沒有權限查詢其他人的消費紀錄！", ephemeral=True)
                return

        spending_data = database.get_user_spending(interaction.guild_id, target_member.id)
        adjustments = database.get_spending_adjustments(
            interaction.guild_id, target_member.id, limit=5
        )

        embed = discord.Embed(
            title=f"💳 消費金額紀錄 - {target_member.display_name}",
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=target_member.display_avatar.url)

        current_month_str = datetime.datetime.now().strftime("%Y年%m月")

        embed.add_field(
            name="💰 總累積消費",
            value=f"**`{format_price(spending_data['total_spending'])}`**",
            inline=True
        )
        embed.add_field(
            name=f"📅 {current_month_str} 當月消費",
            value=f"**`{format_price(spending_data['monthly_spending'])}`**",
            inline=True
        )
        embed.add_field(
            name="📊 結單訂單數",
            value=f"**`{spending_data['completed_count']}` 筆**",
            inline=True
        )

        # 詳細說明細項
        details = (
            f"• 結單訂單累積：`{format_price(spending_data['total_orders_price'])}`\n"
            f"• 本月結單金額：`{format_price(spending_data['monthly_orders_price'])}`\n"
        )
        if spending_data['total_adj'] != 0:
            adj_sign = "+" if spending_data['total_adj'] > 0 else ""
            details += f"• 手動調整累積：`{adj_sign}{format_price(spending_data['total_adj'])}`\n"
        
        embed.add_field(name="ℹ️ 消費明細小計", value=details, inline=False)

        if adjustments:
            adj_text = ""
            for adj in adjustments:
                sign = "+" if adj['amount'] >= 0 else ""
                adj_text += f"`{adj['created_at']}` | **{sign}{format_price(adj['amount'])}** ({adj['reason']})\n"
            embed.add_field(name="📝 最近手動調整紀錄", value=adj_text, inline=False)

        embed.set_footer(text="系統會自動將完成結單的訂單計入消費金額")
        embed.timestamp = datetime.datetime.now(datetime.timezone.utc)

        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Spending(bot))
