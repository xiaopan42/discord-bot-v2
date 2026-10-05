import discord
from discord import app_commands
from discord.ext import commands

import database


async def payment_method_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    if interaction.guild_id is None:
        return []
    current = current.lower()
    return [
        app_commands.Choice(
            name=row["payment_method"], value=row["payment_method"]
        )
        for row in database.get_guild_payment_methods(interaction.guild_id)
        if current in row["payment_method"].lower()
    ][:25]


class PaymentSettings(commands.Cog):
    @app_commands.command(name="設定付款", description="【🏪商城工具】設定本伺服器的付款帳號")
    @app_commands.describe(
        payment_method="付款方式名稱，可輸入新名稱或選擇已有名稱",
        account_info="付款帳號資訊；輸入 clear 可刪除",
    )
    @app_commands.autocomplete(payment_method=payment_method_autocomplete)
    @app_commands.guild_only()
    async def configure(
        self,
        interaction: discord.Interaction,
        payment_method: str,
        account_info: str,
    ):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("你沒有權限使用此指令！", ephemeral=True)
            return

        if account_info.strip().lower() in ("clear", "delete", "刪除", "清除"):
            if database.delete_guild_payment_account(
                interaction.guild_id, payment_method
            ):
                message = f"✅ 已清除 `{payment_method}` 的付款方式。"
            else:
                message = f"找不到 `{payment_method}` 的付款方式設定。"
        else:
            account_info = account_info.replace("\\n", "\n")
            if not account_info.strip():
                await interaction.response.send_message(
                    "付款帳號資訊不可為空白。",
                    ephemeral=True,
                )
                return
            if not payment_method.strip() or len(payment_method.strip()) > 80:
                await interaction.response.send_message(
                    "付款方式名稱不可空白，且不能超過 80 個字元。",
                    ephemeral=True,
                )
                return
            database.set_guild_payment_account(
                interaction.guild_id, payment_method.strip(), account_info
            )
            message = f"✅ 已設定付款方式 `{payment_method.strip()}`。"

        await interaction.response.send_message(message, ephemeral=True)


async def setup(bot):
    await bot.add_cog(PaymentSettings(bot))
