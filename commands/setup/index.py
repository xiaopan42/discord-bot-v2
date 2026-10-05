import discord
from discord import app_commands
from discord.ext import commands

import database


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


class Setup(commands.Cog):
    @app_commands.command(name="設定商品", description="【🏪商城工具】新增或設定出貨商品")
    @app_commands.describe(
        product_name="商品變數名稱，可輸入新名稱或選擇已有名稱",
        channel_id="庫存頻道 ID；輸入 clear 可刪除這個商品",
    )
    @app_commands.autocomplete(product_name=product_autocomplete)
    @app_commands.guild_only()
    async def setup_channel(
        self,
        interaction: discord.Interaction,
        product_name: str,
        channel_id: str,
    ):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("你沒有權限使用此指令！", ephemeral=True)
            return

        product_name = product_name.strip()
        if not product_name or len(product_name) > 80:
            await interaction.response.send_message(
                "商品變數名稱不可空白，且不能超過 80 個字元。",
                ephemeral=True,
            )
            return

        if channel_id.strip().lower() in ("clear", "delete", "刪除", "清除"):
            if database.delete_guild_product(interaction.guild_id, product_name):
                message = f"✅ 已清除商品 `{product_name}`。"
            else:
                message = f"找不到商品 `{product_name}`。"
            await interaction.response.send_message(
                message,
                ephemeral=True,
            )
            return

        try:
            channel = interaction.guild.get_channel(int(channel_id))
        except ValueError:
            channel = None

        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "找不到這個伺服器的文字頻道，請確認頻道 ID 是否正確。",
                ephemeral=True,
            )
            return

        try:
            database.set_guild_product(
                interaction.guild_id, product_name, channel.id
            )
        except ValueError as error:
            await interaction.response.send_message(
                f"設定商品失敗：{error}",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            f"✅ 已將商品 `{product_name}` 設定為庫存頻道 {channel.mention}。",
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(Setup(bot))
