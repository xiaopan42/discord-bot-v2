import discord
from discord import app_commands
from discord.ext import commands, tasks
import database
import json
import sqlite3
import asyncio
import datetime
import math

from config import DISPATCH_CHANNEL_ID

# --- Helper Functions 用於安全產生 Embed ---

DEFAULT_ORDER_DISCLAIMER = (
    "請在開單前確認商品、金額與備註正確。付款將由管理員或客服確認；"
    "需要打手的服務訂單會在確認付款後發送至搶單頻道，商品訂單不會派發搶單。\n\n"
    "如對訂單內容或服務有疑問，請先聯繫客服。點擊下方按鈕代表已閱讀並同意此聲明。"
)


def is_order_staff(member):
    permissions = member.guild_permissions
    return permissions.administrator or permissions.manage_messages


def format_order_value(value):
    text = str(value).replace("`", "'").replace("\n", " ")
    return f"## {text}"


def build_order_embed(order, guild_id):
    if isinstance(order, sqlite3.Row):
        order = dict(order)
    embed = discord.Embed(
        title=f"📝 訂單確認 `#{order['order_num']}`",
        color=discord.Color.blue(),
    )
    status = order['status']
    payment_method = order['payment_method']
    
    if status == 'COMPLETED':
        status_text = "✅ 已結單"
        embed.color = discord.Color.light_grey()
    elif status in ('WAITING', 'IN_PROGRESS'):
        if order.get('players_needed', 0) > 0:
            status_text = "🟢 已付款，已發送搶單"
        else:
            status_text = "🟢 已確認付款，等待結單"
        embed.color = discord.Color.green()
    elif payment_method:
        status_text = "🔴 等待客服確認收款"
        embed.color = discord.Color.gold()
    else:
        status_text = "🟡 請選擇付款方式"
        embed.color = discord.Color.blue()

    remarks = order.get('remarks') or "無"
    embed.description = (
        f"**老闆名稱**\n<@{order['customer_id']}>\n\n"
        f"**購買商品**\n{format_order_value(order['type'])}\n\n"
        f"**此單金額**\n{format_order_value('$' + str(order['price']))}\n\n"
        f"**備註**\n{format_order_value(remarks)}\n\n"
        f"**狀態**\n{format_order_value(status_text)}"
    )
    embed.add_field(
        name="開啟時間",
        value=format_order_value(order.get('created_at') or '未知'),
        inline=False,
    )
    embed.add_field(
        name="結單時間",
        value=format_order_value(order.get('completed_time') or '尚未結單'),
        inline=False,
    )
    if payment_method:
        embed.add_field(
            name="付款方式",
            value=format_order_value(payment_method),
            inline=False,
        )
        account_info = database.get_guild_payment_account(guild_id, payment_method)
        if account_info is None:
            account_info = "此伺服器尚未設定此付款方式，請聯繫管理員。"
        embed.add_field(name="💰 付款帳號資訊", value=f"```\n{account_info}\n```", inline=False)
    return embed

def build_dispatch_embed(order):
    if isinstance(order, sqlite3.Row):
        order = dict(order)
    embed = discord.Embed(
        title=f"🔥 新單搶單中 `#{order['order_num']}`",
        color=discord.Color.orange(),
    )
    
    raw_players = order.get('player_ids')
    try:
        player_ids = json.loads(raw_players) if raw_players else []
    except (json.JSONDecodeError, TypeError):
        player_ids = []
        
    players_needed = order.get('players_needed', 0)
    remarks = order.get('remarks') or "無"
    
    desc = (
        f"**老闆名稱**\n<@{order['customer_id']}>\n\n"
        f"**購買商品**\n{format_order_value(order['type'])}\n\n"
        f"**此單金額**\n{format_order_value('$' + str(order['price']))}\n\n"
        f"**備註**\n{format_order_value(remarks)}\n\n"
    )
    
    for i in range(players_needed):
        if i < len(player_ids):
            desc += f"**打手 ( {i+1} )**\n<@{player_ids[i]}>\n\n"
        else:
            desc += f"**打手 ( {i+1} )**\n等待搶單...\n\n"
            
    if len(player_ids) >= players_needed:
        desc += "**狀態**\n⚔️ 進行中 - 請打手開始服務"
        embed.color = discord.Color.purple()
    else:
        desc += "**狀態**\n⚡ 等待打手搶單"
        embed.color = discord.Color.orange()
        
    embed.description = desc
    return embed

# --- Cog 定義 ---

class Orders(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.auto_review_loop.start()

    def cog_unload(self):
        self.auto_review_loop.cancel()

    @tasks.loop(hours=1)
    async def auto_review_loop(self):
        cutoff = (
            datetime.datetime.now() - datetime.timedelta(hours=24)
        ).strftime("%Y-%m-%d %H:%M:%S")
        for order in database.get_pending_auto_reviews(cutoff):
            await self.submit_auto_review(order)

    @auto_review_loop.before_loop
    async def before_auto_review_loop(self):
        await self.bot.wait_until_ready()

    async def submit_auto_review(self, order):
        guild_id = order["guild_id"]
        settings = database.get_guild_settings(guild_id)
        review_channel_id = settings["review_channel_id"] if settings else None
        if not review_channel_id:
            return
        if not database.try_start_order_review(order["order_num"], guild_id):
            return

        try:
            channel = self.bot.get_channel(int(review_channel_id))
            if channel is None:
                channel = await self.bot.fetch_channel(int(review_channel_id))
            if not isinstance(channel, discord.TextChannel):
                raise ValueError("評價頻道不是文字頻道")

            try:
                customer = await self.bot.fetch_user(int(order["customer_id"]))
            except discord.DiscordException:
                customer = None

            embed = discord.Embed(
                title="<a:1035081379811180556:1538451925966782534> 顧客評價 <a:1035081379811180556:1538451925966782534>",
                color=discord.Color.gold(),
                timestamp=discord.utils.utcnow(),
            )
            if customer:
                embed.set_author(
                    name=customer.display_name,
                    icon_url=customer.display_avatar.url,
                )
                embed.set_thumbnail(url=customer.display_avatar.url)
            else:
                embed.set_author(name=f"老闆 <@{order['customer_id']}>")
            embed.add_field(
                name="<a:arrow_1_6:1541575670826663946>商品名稱",
                value=f"`{order['type']}`",
                inline=False,
            )
            embed.add_field(
                name="<a:arrow_1_6:1541575670826663946>顧客評價",
                value="```超過 24 小時未評價，系統自動給予五星```",
                inline=False,
            )
            embed.add_field(
                name="<a:arrow_1_6:1541575670826663946>滿意程度",
                value="⭐⭐⭐⭐⭐ (5/5)",
                inline=False,
            )
            embed.set_footer(
                text=f"星核娛樂機器人丨{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            await channel.send(embed=embed)
        except (discord.DiscordException, ValueError) as error:
            database.cancel_order_review(order["order_num"], guild_id)
            print(f"自動評價發送失敗（訂單 {order['order_num']}）：{error}")

    @app_commands.command(name="訂單工具", description="【🏪商城工具】先填寫訂單，再請客人確認")
    @app_commands.guild_only()
    @app_commands.describe(customer="請選擇或 @標記老闆")
    async def order(self, interaction: discord.Interaction, customer: discord.Member):
        if not is_order_staff(interaction.user):
            await interaction.response.send_message(
                "只有管理員或客服可以使用此指令！",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(
            OrderModal(customer, str(interaction.user.id))
        )

    @app_commands.command(name="設定訂單免責聲明", description="【管理員專用】設定本伺服器開單時顯示的免責聲明")
    @app_commands.guild_only()
    async def set_order_disclaimer(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "只有管理員可以修改訂單免責聲明。",
                ephemeral=True,
            )
            return
        settings = database.get_guild_settings(interaction.guild_id)
        current = settings["order_disclaimer"] if settings else None
        await interaction.response.send_modal(
            OrderDisclaimerModal(current or DEFAULT_ORDER_DISCLAIMER)
        )

async def setup(bot):
    await bot.add_cog(Orders(bot))

# --- 介面組件 ---

class OrderDisclaimerView(discord.ui.View):
    def __init__(self, customer_id, order_details, admin_id, guild_id):
        super().__init__(timeout=86400)
        self.customer_id = str(customer_id)
        self.order_details = order_details
        self.admin_id = str(admin_id)
        self.guild_id = str(guild_id)
        self.accept_lock = asyncio.Lock()
        self.accepted = False

    @discord.ui.button(
        label="我已閱讀並確認訂單內容",
        style=discord.ButtonStyle.success,
        custom_id=None,
    )
    async def accept_order(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.customer_id:
            await interaction.response.send_message(
                "只有這張訂單指定的客人可以確認。",
                ephemeral=True,
            )
            return
        if interaction.guild_id is None or str(interaction.guild_id) != self.guild_id:
            await interaction.response.send_message(
                "此訂單只能在建立它的伺服器中確認。",
                ephemeral=True,
            )
            return

        async with self.accept_lock:
            if self.accepted:
                await interaction.response.send_message(
                    "這筆訂單已經確認建立。",
                    ephemeral=True,
                )
                return
            self.accepted = True
            try:
                order_num = database.create_order(
                    self.guild_id,
                    self.customer_id,
                    self.order_details["order_type"],
                    self.order_details["price"],
                    self.order_details["players_needed"],
                    self.order_details["remarks"],
                    self.admin_id,
                    interaction.message.id,
                    interaction.message.channel.id,
                )
                order = database.get_order(order_num, self.guild_id)
                payment_view = PaymentSelectView(order_num, self.guild_id)
                interaction.client.add_view(payment_view)
            except sqlite3.Error as error:
                self.accepted = False
                print(f"客人確認後建立訂單失敗：{error}")
                await interaction.response.send_message(
                    "建立訂單失敗，請通知管理員或客服重新開單。",
                    ephemeral=True,
                )
                return
            await interaction.response.edit_message(
                embed=build_order_embed(order, self.guild_id),
                view=payment_view,
            )

class OrderDisclaimerModal(discord.ui.Modal, title="設定本伺服器訂單免責聲明"):
    disclaimer = discord.ui.TextInput(
        label="免責聲明內容",
        placeholder="輸入本伺服器開單時要顯示的文字",
        style=discord.TextStyle.paragraph,
        max_length=4000,
        required=True,
    )

    def __init__(self, current_disclaimer):
        super().__init__()
        self.disclaimer.default = current_disclaimer[:4000]

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "只有管理員可以修改訂單免責聲明。",
                ephemeral=True,
            )
            return
        content = self.disclaimer.value.strip()
        if content == "重設預設":
            database.set_guild_order_disclaimer(interaction.guild_id, None)
            await interaction.response.send_message(
                "已恢復系統預設的訂單免責聲明。",
                ephemeral=True,
            )
            return
        if not content:
            await interaction.response.send_message(
                "免責聲明不可為空白；若要恢復預設，請輸入「重設預設」。",
                ephemeral=True,
            )
            return
        database.set_guild_order_disclaimer(interaction.guild_id, content)
        await interaction.response.send_message(
            "已更新本伺服器的訂單免責聲明。",
            ephemeral=True,
        )


class OrderModal(discord.ui.Modal, title='星核娛樂俱樂部 開單系統'):
    def __init__(self, customer: discord.Member, admin_id: str):
        super().__init__()
        self.customer_id = str(customer.id)
        self.admin_id = admin_id

    order_type = discord.ui.TextInput(label='購買商品或服務', placeholder='請輸入商品名稱或服務類型')
    players_needed = discord.ui.TextInput(label='需要打手數量', placeholder='商品訂單填 0', default="0")
    price = discord.ui.TextInput(label='此單價格', placeholder='請輸入數字')
    remarks = discord.ui.TextInput(label='備註', placeholder='請輸入訂單詳細要求', style=discord.TextStyle.paragraph, required=False)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            price_val = float(self.price.value)
            players_val = int(self.players_needed.value)
        except (TypeError, ValueError):
            await interaction.response.send_message("價格與數量請輸入有效數字！", ephemeral=True)
            return
        if not math.isfinite(price_val) or price_val < 0:
            await interaction.response.send_message(
                "價格必須是大於或等於 0 的有效數字！",
                ephemeral=True,
            )
            return
        if players_val < 0:
            await interaction.response.send_message(
                "打手數量不可小於 0！",
                ephemeral=True,
            )
            return

        if interaction.guild_id is None:
            await interaction.response.send_message(
                "只能在伺服器內建立訂單。",
                ephemeral=True,
            )
            return

        settings = database.get_guild_settings(interaction.guild_id)
        disclaimer_text = (
            settings["order_disclaimer"]
            if settings and settings["order_disclaimer"]
            else DEFAULT_ORDER_DISCLAIMER
        )
        disclaimer = discord.Embed(
            title="📋 訂單免責聲明",
            description=disclaimer_text,
            color=discord.Color.gold(),
        )
        view = OrderDisclaimerView(
            self.customer_id,
            {
                "order_type": self.order_type.value.strip(),
                "price": price_val,
                "players_needed": players_val,
                "remarks": self.remarks.value.strip() or "無",
            },
            self.admin_id,
            interaction.guild_id,
        )
        await interaction.response.send_message(
            content=f"<@{self.customer_id}> 請閱讀免責聲明並確認下方按鈕，確認前不會建立訂單。",
            embed=disclaimer,
            view=view,
            allowed_mentions=discord.AllowedMentions(users=True),
        )

class PaymentSelectView(discord.ui.View):
    def __init__(self, order_num, guild_id):
        super().__init__(timeout=None)
        self.order_num = order_num
        self.guild_id = guild_id
        methods = database.get_guild_payment_methods(guild_id)
        options = [
            discord.SelectOption(label=row["payment_method"])
            for row in methods
        ]
        if not options:
            options = [
                discord.SelectOption(
                    label="尚未設定付款方式",
                    value="__no_payment_method__",
                )
            ]
        self.select_menu = discord.ui.Select(
            placeholder="選擇付款方式...",
            options=options,
            custom_id=f"pay_select_{order_num}",
        )
        self.select_menu.callback = self.select_menu_callback
        self.add_item(self.select_menu)

    async def select_menu_callback(self, interaction: discord.Interaction):
        if not is_order_staff(interaction.user):
            await interaction.response.send_message(
                "只有管理員或客服可以選擇付款方式。",
                ephemeral=True,
            )
            return
        await interaction.response.defer()
        method = self.select_menu.values[0]
        if method == "__no_payment_method__":
            await interaction.followup.send(
                "此伺服器尚未設定付款方式，請先使用 `/設定付款`。",
                ephemeral=True,
            )
            return
        updated = database.update_order_payment(
            self.order_num,
            method,
            self.guild_id,
            expected_status="PENDING",
        )
        if not updated:
            await interaction.followup.send(
                "這張訂單已經不是待付款狀態，付款按鈕可能已失效。",
                ephemeral=True,
            )
            return
        order = database.get_order(self.order_num, self.guild_id)
        embed = build_order_embed(order, self.guild_id)
        next_view = AdminConfirmPaymentView(self.order_num, self.guild_id)
        interaction.client.add_view(next_view)
        await interaction.message.edit(embed=embed, view=next_view)

class ReviewView(discord.ui.View):
    def __init__(self, order_num, guild_id, customer_id, product_name):
        super().__init__(timeout=None)
        self.order_num = order_num
        self.guild_id = guild_id
        self.customer_id = str(customer_id)
        self.product_name = product_name
        self.review_btn.custom_id = f"review_{order_num}"

    @discord.ui.button(
        label="留下評價",
        emoji="⭐",
        style=discord.ButtonStyle.primary,
        custom_id="review_default",
    )
    async def review_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.customer_id:
            await interaction.response.send_message(
                "只有這張訂單的老闆可以留下評價。",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(
            ReviewModal(
                self.order_num,
                self.guild_id,
                self.customer_id,
                self.product_name,
            )
        )

class ReviewModal(discord.ui.Modal, title="星核娛樂｜訂單評價"):
    comment = discord.ui.TextInput(
        label="評論",
        placeholder="請輸入您對本次服務的評論",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=True,
    )
    stars = discord.ui.TextInput(
        label="評價星數（1-5）",
        placeholder="請輸入 1 到 5",
        max_length=1,
        required=True,
    )

    def __init__(self, order_num, guild_id, customer_id, product_name):
        super().__init__()
        self.order_num = order_num
        self.guild_id = guild_id
        self.customer_id = str(customer_id)
        self.product_name = product_name

    async def on_submit(self, interaction: discord.Interaction):
        try:
            stars = int(self.stars.value.strip())
        except ValueError:
            await interaction.response.send_message(
                "星數必須是 1 到 5 的整數。",
                ephemeral=True,
            )
            return
        if not 1 <= stars <= 5:
            await interaction.response.send_message(
                "星數必須介於 1 到 5。",
                ephemeral=True,
            )
            return

        settings = database.get_guild_settings(self.guild_id)
        review_channel_id = settings["review_channel_id"] if settings else None
        if not review_channel_id:
            await interaction.response.send_message(
                "此伺服器尚未設定評價頻道，請聯繫管理員。",
                ephemeral=True,
            )
            return

        if not database.try_start_order_review(self.order_num, self.guild_id):
            await interaction.response.send_message(
                "這張訂單已經提交過評價，每張訂單只能評價一次。",
                ephemeral=True,
            )
            return

        try:
            channel = interaction.client.get_channel(int(review_channel_id))
            if channel is None:
                channel = await interaction.client.fetch_channel(int(review_channel_id))
            if not isinstance(channel, discord.TextChannel):
                raise ValueError("評價頻道不是文字頻道")

            embed = discord.Embed(
                title="<a:1035081379811180556:1538451925966782534> 顧客評價 <a:1035081379811180556:1538451925966782534>",
                color=discord.Color.gold(),
                timestamp=discord.utils.utcnow(),
            )
            embed.set_author(
                name=interaction.user.display_name,
                icon_url=interaction.user.display_avatar.url,
            )
            embed.set_thumbnail(url=interaction.user.display_avatar.url)
            embed.add_field(
                name="<a:arrow_1_6:1541575670826663946>商品名稱",
                value=f"`{self.product_name}`",
                inline=False,
            )
            embed.add_field(
                name="<a:arrow_1_6:1541575670826663946>客戶評論",
                value=f"```{self.comment.value}```",
                inline=False,
            )
            embed.add_field(
                name=f"<a:arrow_1_6:1541575670826663946>滿意程度({stars}/5)",
                value=f"{'⭐' * stars} ",
                inline=False,
            )
            embed.set_footer(
                text=f"星核娛樂機器人丨{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            await channel.send(embed=embed)
        except (discord.DiscordException, ValueError) as error:
            database.cancel_order_review(self.order_num, self.guild_id)
            await interaction.response.send_message(
                f"發送評價失敗：{error}",
                ephemeral=True,
            )
            return

        await interaction.response.send_message("✅ 感謝您的評價！", ephemeral=True)

class AdminConfirmPaymentView(discord.ui.View):
    def __init__(self, order_num, guild_id):
        super().__init__(timeout=None)
        self.order_num = order_num
        self.guild_id = guild_id
        self.confirm_btn.custom_id = f"admin_confirm_{order_num}"

    @discord.ui.button(label="確認已收款", style=discord.ButtonStyle.green, custom_id="admin_confirm_default")
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_order_staff(interaction.user):
            await interaction.response.send_message("只有客服可以確認收款！", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        order = database.get_order(self.order_num, self.guild_id)
        if not order:
            await interaction.followup.send("找不到訂單資料！", ephemeral=True)
            return
        if order["status"] != "PENDING":
            await interaction.followup.send(
                "這張訂單目前不是待確認付款狀態，按鈕可能已失效。",
                ephemeral=True,
            )
            return
        
        if order['players_needed'] == 0:
            updated = database.update_order_status(
                self.order_num,
                'IN_PROGRESS',
                self.guild_id,
                expected_status='PENDING',
            )
            if not updated:
                await interaction.followup.send(
                    "這張訂單已被其他操作更新，請重新整理後再試。",
                    ephemeral=True,
                )
                return
            updated_order = database.get_order(self.order_num, self.guild_id)
            embed = build_order_embed(updated_order, self.guild_id)
            close_view = PlayerCompleteView(self.order_num, self.guild_id)
            interaction.client.add_view(close_view)
            await interaction.message.edit(embed=embed, view=close_view)
            await interaction.followup.send(
                "付款已確認，商品訂單不會發送搶單；請於完成後按「完成結單」。",
                ephemeral=True,
            )
        else:
            updated = database.update_order_status(
                self.order_num,
                'WAITING',
                self.guild_id,
                expected_status='PENDING',
            )
            if not updated:
                await interaction.followup.send(
                    "這張訂單已被其他操作更新，請重新整理後再試。",
                    ephemeral=True,
                )
                return
            updated_order = database.get_order(self.order_num, self.guild_id)
            
            settings = database.get_guild_settings(self.guild_id)
            dispatch_id = (
                settings["dispatch_channel_id"] if settings else None
            ) or DISPATCH_CHANNEL_ID
            if dispatch_id:
                try:
                    dispatch_channel = interaction.client.get_channel(int(dispatch_id)) or await interaction.client.fetch_channel(int(dispatch_id))
                    if getattr(dispatch_channel, "guild", None) and dispatch_channel.guild.id != self.guild_id:
                        dispatch_channel = None
                except Exception:
                    dispatch_channel = None

                if dispatch_channel:
                    try:
                        dispatch_embed = build_dispatch_embed(updated_order)
                        view = PlayerClaimView(
                            self.order_num,
                            updated_order['players_needed'],
                            self.guild_id,
                        )
                        interaction.client.add_view(view)
                        msg = await dispatch_channel.send(
                            embed=dispatch_embed,
                            view=view,
                        )
                    except discord.DiscordException as error:
                        database.update_order_status(
                            self.order_num,
                            'PENDING',
                            self.guild_id,
                            expected_status='WAITING',
                        )
                        restored_order = database.get_order(
                            self.order_num,
                            self.guild_id,
                        )
                        restored_view = AdminConfirmPaymentView(
                            self.order_num,
                            self.guild_id,
                        )
                        interaction.client.add_view(restored_view)
                        await interaction.message.edit(
                            embed=build_order_embed(
                                restored_order,
                                self.guild_id,
                            ),
                            view=restored_view,
                        )
                        await interaction.followup.send(
                            f"發送接單訊息失敗，訂單已恢復待確認狀態：{error}",
                            ephemeral=True,
                        )
                        return
                    database.update_order_message(
                        self.order_num,
                        msg.id,
                        dispatch_channel.id,
                        self.guild_id,
                    )
                    await interaction.message.edit(
                        embed=build_order_embed(updated_order, self.guild_id),
                        view=None,
                    )
                    await interaction.followup.send(
                        "訂單已發送至接單頻道！",
                        ephemeral=True,
                    )
                else:
                    database.update_order_status(
                        self.order_num,
                        'PENDING',
                        self.guild_id,
                        expected_status='WAITING',
                    )
                    restored_order = database.get_order(
                        self.order_num,
                        self.guild_id,
                    )
                    restored_view = AdminConfirmPaymentView(
                        self.order_num,
                        self.guild_id,
                    )
                    interaction.client.add_view(restored_view)
                    await interaction.message.edit(
                        embed=build_order_embed(
                            restored_order,
                            self.guild_id,
                        ),
                        view=restored_view,
                    )
                    await interaction.followup.send(
                        "找不到接單頻道，訂單已恢復待確認狀態。",
                        ephemeral=True,
                    )
            else:
                database.update_order_status(
                    self.order_num,
                    'PENDING',
                    self.guild_id,
                    expected_status='WAITING',
                )
                restored_order = database.get_order(
                    self.order_num,
                    self.guild_id,
                )
                restored_view = AdminConfirmPaymentView(
                    self.order_num,
                    self.guild_id,
                )
                interaction.client.add_view(restored_view)
                await interaction.message.edit(
                    embed=build_order_embed(
                        restored_order,
                        self.guild_id,
                    ),
                    view=restored_view,
                )
                await interaction.followup.send(
                    "未設定接單頻道，訂單已恢復待確認狀態。",
                    ephemeral=True,
                )

    async def send_dm_to_customer(self, interaction, order):
        try:
            customer = await interaction.client.fetch_user(int(order['customer_id']))
            dm_embed = discord.Embed(title="✨ 訂單結單內容", color=discord.Color.gold())
            dm_embed.description = (
                f"**老闆名稱**\n<@{order['customer_id']}>\n\n"
                f"**訂單編號**\n{format_order_value(order['order_num'])}\n\n"
                f"**購買商品**\n{format_order_value(order['type'])}\n\n"
                f"**訂單開啟時間**\n{format_order_value(order['created_at'] or '未知')}\n\n"
                f"**結單時間**\n{format_order_value(order['completed_time'] or '未知')}\n\n"
                f"**金額**\n{format_order_value('$' + str(order['price']))}"
            )
            await customer.send(embed=dm_embed)
        except Exception as e:
            print(f"發送私訊給老闆失敗: {e}")

    async def send_to_log_channel(self, interaction, order, player_ids):
        settings = database.get_guild_settings(self.guild_id)
        log_id = settings["log_channel_id"] if settings else None
        if log_id:
            try:
                log_channel = interaction.client.get_channel(int(log_id)) or await interaction.client.fetch_channel(int(log_id))
            except Exception:
                log_channel = None

            if log_channel:
                final_embed = discord.Embed(
                    title=f"✅ 結單紀錄 `#{order['order_num']}`",
                    color=discord.Color.light_grey(),
                )
                player_mentions = "\n".join([f"**打手 ( {i+1} )**\n<@{pid}>" for i, pid in enumerate(player_ids)])
                player_summary = player_mentions if player_ids else "**負責打手**\n無 (一般訂單)"
                remarks = order['remarks'] or '無'
                final_embed.description = (
                    f"**老闆名稱**\n<@{order['customer_id']}>\n\n"
                    f"**購買商品**\n{format_order_value(order['type'])}\n\n"
                    f"**此單金額**\n{format_order_value('$' + str(order['price']))}\n\n"
                    f"{player_summary}\n\n"
                    f"**付款方式**\n{format_order_value(order['payment_method'])}\n\n"
                    f"**備註**\n{format_order_value(remarks)}"
                )
                await log_channel.send(embed=final_embed)

class PlayerClaimView(discord.ui.View):
    def __init__(self, order_num, players_needed, guild_id):
        super().__init__(timeout=None)
        self.order_num = order_num
        self.players_needed = players_needed
        self.guild_id = guild_id
        order = database.get_order(order_num, guild_id)
        
        raw_players = order['player_ids'] if order else '[]'
        try:
            current_player_ids = json.loads(raw_players) if raw_players else []
        except (json.JSONDecodeError, TypeError):
            current_player_ids = []

        for i in range(players_needed):
            if i < len(current_player_ids):
                pid = current_player_ids[i]
                btn = discord.ui.Button(
                    label=f"打手 {i+1} 已搶單",
                    style=discord.ButtonStyle.secondary,
                    disabled=True,
                    custom_id=f"claim_{order_num}_{i}"
                )
            else:
                btn = discord.ui.Button(
                    label=f"搶單 {i+1}",
                    style=discord.ButtonStyle.primary,
                    custom_id=f"claim_{order_num}_{i}"
                )
                btn.callback = self.make_callback(i)
            self.add_item(btn)

    def make_callback(self, index):
        async def callback(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            order = database.get_order(self.order_num, self.guild_id)
            if not order:
                await interaction.followup.send("找不到訂單資料！", ephemeral=True)
                return
            
            raw_players = order['player_ids']
            try:
                player_ids = json.loads(raw_players) if raw_players else []
            except Exception:
                player_ids = []

            if str(interaction.user.id) in player_ids:
                await interaction.followup.send("你已經搶過這單囉！", ephemeral=True)
                return

            success, new_player_ids = database.add_player_to_order(self.order_num, str(interaction.user.id), self.guild_id)
            if success:
                updated_order = database.get_order(self.order_num, self.guild_id)
                dispatch_embed = build_dispatch_embed(updated_order)
                
                if len(new_player_ids) >= self.players_needed:
                    updated_order = database.get_order(self.order_num, self.guild_id)
                    dispatch_embed = build_dispatch_embed(updated_order)
                    next_view = PlayerCompleteView(self.order_num, self.guild_id)
                    interaction.client.add_view(next_view)
                    await interaction.message.edit(embed=dispatch_embed, view=next_view)
                else:
                    next_view = PlayerClaimView(self.order_num, self.players_needed, self.guild_id)
                    interaction.client.add_view(next_view)
                    await interaction.message.edit(embed=dispatch_embed, view=next_view)
                
                await interaction.followup.send("搶單成功！", ephemeral=True)
            else:
                await interaction.followup.send(
                    "這張訂單已經不能再搶單，可能已取消或已被其他人搶滿。",
                    ephemeral=True,
                )
        return callback

class PlayerCompleteView(discord.ui.View):
    def __init__(self, order_num, guild_id):
        super().__init__(timeout=None)
        self.order_num = order_num
        self.guild_id = guild_id
        self.complete_btn.custom_id = f"complete_{order_num}"

    @discord.ui.button(label="完成結單", style=discord.ButtonStyle.success, custom_id="complete_default")
    async def complete_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        order = database.get_order(self.order_num, self.guild_id)
        if not order:
            await interaction.response.send_message("找不到訂單資料！", ephemeral=True)
            return
        if order["status"] != "IN_PROGRESS":
            await interaction.response.send_message(
                "這張訂單目前不是進行中，按鈕可能已失效。",
                ephemeral=True,
            )
            return

        raw_players = order['player_ids']
        try:
            player_ids = json.loads(raw_players) if raw_players else []
        except Exception:
            player_ids = []

        if str(interaction.user.id) not in player_ids and not is_order_staff(interaction.user):
            await interaction.response.send_message("只有負責的打手或客服可以結單！", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        updated = database.update_order_status(
            self.order_num,
            'COMPLETED',
            self.guild_id,
            expected_status='IN_PROGRESS',
        )
        if not updated:
            await interaction.followup.send(
                "這張訂單已被其他操作完成，請勿重複結單。",
                ephemeral=True,
            )
            return
        updated_order = database.get_order(self.order_num, self.guild_id)

        helper = AdminConfirmPaymentView(self.order_num, self.guild_id)
        review_view = ReviewView(
            self.order_num,
            self.guild_id,
            updated_order["customer_id"],
            updated_order["type"],
        )
        interaction.client.add_view(review_view)
        ticket_message_id = updated_order["ticket_msg_id"]
        ticket_update_error = None
        if ticket_message_id and str(interaction.message.id) != str(ticket_message_id):
            await interaction.message.edit(
                embed=build_order_embed(updated_order, self.guild_id),
                view=None,
            )
            ticket_channel_id = updated_order["ticket_channel_id"]
            if not ticket_channel_id:
                ticket_update_error = "找不到客服單頻道"
            else:
                try:
                    ticket_channel = interaction.client.get_channel(int(ticket_channel_id))
                    if ticket_channel is None:
                        ticket_channel = await interaction.client.fetch_channel(
                            int(ticket_channel_id)
                        )
                    if not isinstance(
                        ticket_channel, (discord.TextChannel, discord.Thread)
                    ):
                        raise ValueError("客服單頻道不是文字頻道或討論串")
                    ticket_message = await ticket_channel.fetch_message(
                        int(ticket_message_id)
                    )
                    await ticket_message.edit(
                        embed=build_order_embed(updated_order, self.guild_id),
                        view=review_view,
                    )
                except (ValueError, discord.DiscordException) as error:
                    ticket_update_error = str(error)
                    print(
                        f"結單後更新客服單評價按鈕失敗（訂單 {self.order_num}）：{error}"
                    )
        else:
            await interaction.message.edit(
                embed=build_order_embed(updated_order, self.guild_id),
                view=review_view,
            )
        await helper.send_dm_to_customer(interaction, updated_order)
        await helper.send_to_log_channel(interaction, updated_order, player_ids)
        database.export_orders_to_excel()

        response = "結單完成！已自動私訊老闆與發送日誌。"
        if ticket_update_error:
            response += f" 但無法在客服單放置評價按鈕：{ticket_update_error}"
        await interaction.followup.send(response, ephemeral=True)
