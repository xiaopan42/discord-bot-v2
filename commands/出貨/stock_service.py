"""出貨與庫存指令共用的庫存讀取與日誌功能。"""

import discord

import database


def parse_stock_message(message: discord.Message) -> list[dict]:
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


async def get_available_stock(bot: discord.Client, product_name: str, guild_id: int) -> list[dict]:
    channel_id = database.get_guild_product_channel(guild_id, product_name)
    if not channel_id:
        raise ValueError(f"尚未設定商品 `{product_name}`，請先使用 /setup")
    channel_id = int(channel_id)
    channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
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


async def send_shipment_log(bot: discord.Client, interaction: discord.Interaction, product_name: str, quantity: int) -> None:
    try:
        settings = database.get_guild_settings(interaction.guild_id)
        log_id = settings["shipping_log_channel_id"] if settings else None
        if not log_id:
            return
        channel = bot.get_channel(int(log_id)) or await bot.fetch_channel(int(log_id))
        embed = discord.Embed(title="📝 出貨系統日誌", color=discord.Color.blurple(), timestamp=discord.utils.utcnow())
        embed.add_field(name="商品", value=product_name, inline=True)
        embed.add_field(name="數量", value=str(quantity), inline=True)
        embed.add_field(name="執行人員", value=f"{interaction.user.mention}\n`{interaction.user.id}`", inline=False)
        embed.add_field(name="執行頻道", value=f"{interaction.channel.mention}\n`{interaction.channel_id}`", inline=False)
        await channel.send(embed=embed)
    except discord.DiscordException as error:
        print(f"出貨日誌發送失敗：{error}")
