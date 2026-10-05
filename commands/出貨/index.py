import asyncio
import discord
from discord import app_commands
from discord.ext import commands

import database


def parse_stock_message(message):
    """將一則庫存訊息中的「帳號 密碼」逐行解析為庫存資料。"""
    items = []
    for line_number, line in enumerate(message.content.splitlines(), start=1):
        parts = line.strip().split(maxsplit=1)
        if len(parts) != 2:
            continue
        account, password = parts
        items.append({
            "message_id": message.id,
            "line_number": line_number,
            "account": account,
            "password": password,
        })
    return items


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


class Stock(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.shipment_lock = asyncio.Lock()

    async def get_available_stock(self, product_name, guild_id):
        channel_id = database.get_guild_product_channel(guild_id, product_name)
        channel_id = int(channel_id) if channel_id else None
        if not channel_id:
            raise ValueError(f"尚未設定商品 `{product_name}`，請先使用 /setup")
        channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            raise ValueError("設定的庫存頻道不是文字頻道")

        shipped_keys = database.get_shipped_stock_keys(channel_id, guild_id)
        shipped_accounts = database.get_shipped_stock_accounts(product_name, guild_id)
        available = []
        async for message in channel.history(limit=None, oldest_first=True):
            for item in parse_stock_message(message):
                key = (str(item["message_id"]), item["line_number"])
                if key not in shipped_keys and item["account"] not in shipped_accounts:
                    available.append(item)
        return available

    async def send_shipment_log(self, interaction, product_name, quantity):
        """將成功出貨紀錄寫入指定日誌頻道，不包含帳號密碼。"""
        try:
            settings = database.get_guild_settings(interaction.guild_id)
            log_id = settings["shipping_log_channel_id"] if settings else None
            if not log_id:
                return
            log_channel = (
                self.bot.get_channel(int(log_id))
                or await self.bot.fetch_channel(int(log_id))
            )
            log_embed = discord.Embed(
                title="📦 出貨系統日誌",
                color=discord.Color.blurple(),
                timestamp=discord.utils.utcnow(),
            )
            log_embed.add_field(name="商品", value=product_name, inline=True)
            log_embed.add_field(name="數量", value=str(quantity), inline=True)
            log_embed.add_field(
                name="執行人員",
                value=f"{interaction.user.mention}\n`{interaction.user.id}`",
                inline=False,
            )
            log_embed.add_field(
                name="執行頻道",
                value=f"{interaction.channel.mention}\n`{interaction.channel_id}`",
                inline=False,
            )
            log_embed.set_footer(text="出貨時間")
            await log_channel.send(embed=log_embed)
        except discord.DiscordException as error:
            print(f"出貨日誌發送失敗：{error}")

    @app_commands.command(name="出貨", description="【🏪商城工具】從庫存頻道取出尚未出貨的帳號")
    @app_commands.guild_only()
    @app_commands.describe(product="要出貨的商品", quantity="出貨數量")
    @app_commands.autocomplete(product=product_autocomplete)
    async def ship(
        self,
        interaction: discord.Interaction,
        product: str,
        quantity: app_commands.Range[int, 1, 50],
    ):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("你沒有權限使用此指令！", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        async with self.shipment_lock:
            try:
                available = await self.get_available_stock(product, interaction.guild_id)
            except (discord.DiscordException, ValueError) as error:
                await interaction.followup.send(
                    f"讀取庫存頻道失敗：{error}",
                    ephemeral=True,
                )
                return

            selected = available[:quantity]
            if len(selected) < quantity:
                await interaction.followup.send(
                    f"⚠️ `{product}` 庫存不足：目前僅剩 `{len(selected)}` 個，未建立出貨紀錄。",
                    ephemeral=True,
                )
                return

            channel_id = database.get_guild_product_channel(
                interaction.guild_id, product
            )
            if not channel_id:
                await interaction.followup.send(
                    f"尚未設定商品 `{product}`，請先使用 `/setup`。",
                    ephemeral=True,
                )
                return
            recorded = database.record_stock_shipments(
                interaction.guild_id, product, int(channel_id), selected, interaction.user.id
            )
            if recorded != quantity:
                await interaction.followup.send(
                    "出貨紀錄發生衝突，庫存未被取出，請重新執行指令。",
                    ephemeral=True,
                )
                return

        await self.send_shipment_log(interaction, product, quantity)

        account_lines = "\n".join(f"{item['account']} {item['password']}" for item in selected)
        if len(account_lines) <= 900:
            embed = discord.Embed(title="✅ 出貨系統", color=discord.Color.green())
            embed.add_field(name="商品", value=product, inline=True)
            embed.add_field(name="數量", value=str(quantity), inline=True)
            embed.add_field(
                name="帳號資料",
                value=f"```\n{account_lines}\n```",
                inline=False,
            )
            embed.set_footer(text="星核娛樂機器人 - SC CLUB BOT")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Discord Embed 欄位有長度限制；長庫存改用多則私訊回覆，避免出貨成功後回覆失敗。
        chunks = [
            account_lines[index:index + 1800]
            for index in range(0, len(account_lines), 1800)
        ]
        for index, chunk in enumerate(chunks):
            header = (
                f"✅ 出貨系統｜商品：`{product}`｜數量：`{quantity}`\n"
                if index == 0
                else "✅ 出貨帳號資料（續）\n"
            )
            await interaction.followup.send(
                f"{header}```\n{chunk}\n```",
                ephemeral=True,
            )

async def setup(bot):
    await bot.add_cog(Stock(bot))
