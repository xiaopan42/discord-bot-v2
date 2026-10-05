import discord
from discord import app_commands
from discord.ext import commands

import database


class GuildSettings(commands.Cog):
    @app_commands.command(name="頻道設定", description="【🏪商城工具】】設定本伺服器的機器人頻道")
    @app_commands.describe(
        dispatch_channel="訂單接單頻道",
        log_channel="訂單結單日誌頻道",
        review_channel="顧客評價發布頻道",
        shipping_log_channel="出貨日誌頻道",
    )
    @app_commands.guild_only()
    async def configure(
        self,
        interaction: discord.Interaction,
        dispatch_channel: discord.TextChannel = None,
        log_channel: discord.TextChannel = None,
        review_channel: discord.TextChannel = None,
        shipping_log_channel: discord.TextChannel = None,
    ):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("你沒有權限使用此指令！", ephemeral=True)
            return

        if not any((dispatch_channel, log_channel, review_channel, shipping_log_channel)):
            await interaction.response.send_message("至少要設定一個頻道。", ephemeral=True)
            return

        current = database.get_guild_settings(interaction.guild_id)
        get_current = lambda name: current[name] if current else None
        database.set_guild_settings(
            interaction.guild_id,
            dispatch_channel.id if dispatch_channel else get_current("dispatch_channel_id"),
            log_channel.id if log_channel else get_current("log_channel_id"),
            review_channel.id if review_channel else get_current("review_channel_id"),
            get_current("stock_100m_channel_id"),
            get_current("stock_200m_channel_id"),
            shipping_log_channel.id if shipping_log_channel else get_current("shipping_log_channel_id"),
        )
        await interaction.response.send_message(
            "已設定成功。",
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(GuildSettings(bot))
