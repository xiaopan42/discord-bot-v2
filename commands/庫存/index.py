import discord
from discord import app_commands
from discord.ext import commands

import database

from commands.出貨.stock_service import get_available_stock


async def product_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    if interaction.guild_id is None:
        return []
    current = current.lower()
    return [
        app_commands.Choice(name=row["product_name"], value=row["product_name"])
        for row in database.get_guild_products(interaction.guild_id)
        if current in row["product_name"].lower()
    ][:25]


class StockCount(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="庫存", description="【🔨管理員專用】查看指定商品的剩餘帳號數量")
    @app_commands.guild_only()
    @app_commands.describe(product="要查詢的商品")
    @app_commands.autocomplete(product=product_autocomplete)
    async def stock_count(self, interaction: discord.Interaction, product: str):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("你沒有權限使用此指令！", ephemeral=True)
            return

        await interaction.response.defer()
        try:
            if interaction.guild_id is None:
                await interaction.followup.send("此指令只能在伺服器內使用。")
                return
            available = await get_available_stock(self.bot, product, interaction.guild_id)
        except (discord.DiscordException, ValueError) as error:
            await interaction.followup.send(f"讀取庫存頻道失敗：{error}")
            return
        await interaction.followup.send(f"📝 `{product}` 目前剩餘 `{len(available)}` 個。")


async def setup(bot):
    await bot.add_cog(StockCount(bot))
