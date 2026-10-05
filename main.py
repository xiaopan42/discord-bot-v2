import discord
from discord.ext import commands
import database
import os
import sys
import asyncio
from config import BASE_DIR, TOKEN, DISPATCH_CHANNEL_ID

if hasattr(sys.stdout, 'reconfigure'):
    try: sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception: pass
if hasattr(sys.stderr, 'reconfigure'):
    try: sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception: pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        activity = discord.Game(name="0.8 version | BY CS CLUB")
        
        super().__init__(
            command_prefix="!", 
            intents=intents,
            activity=activity,
            status=discord.Status.online
        )

    async def setup_hook(self):
        # 1. 初始化資料庫
        database.init_db()

        # 2. 將舊版資料庫中沒有 guild_id 的進行中訂單補回所屬伺服器。
        #    優先使用訂單原本記錄的接單頻道，舊訂單則使用舊版環境變數。
        legacy_orders = database.get_active_orders()
        for legacy_order in legacy_orders:
            if legacy_order['guild_id']:
                continue
            channel_id = legacy_order['dispatch_channel_id'] or DISPATCH_CHANNEL_ID
            if not channel_id:
                continue
            try:
                channel = self.get_channel(int(channel_id))
                if channel is None:
                    channel = await self.fetch_channel(int(channel_id))
                if getattr(channel, 'guild', None):
                    database.set_order_guild_id(
                        legacy_order['order_num'], channel.guild.id
                    )
                    print(
                        f"✅ 已補回訂單 {legacy_order['order_num']} "
                        f"的伺服器 ID：{channel.guild.id}"
                    )
            except (ValueError, discord.DiscordException) as error:
                print(f"⚠️ 無法補回訂單 {legacy_order['order_num']} 的伺服器 ID：{error}")
        
        # 3. 自動載入指令模組
        commands_dir = BASE_DIR / 'commands'
        if not commands_dir.exists():
            commands_dir.mkdir(parents=True)
            print("已自動建立 commands 資料夾")
        
        for root, dirs, files in os.walk(commands_dir):
            dirs.sort()
            for filename in sorted(files):
                # 每個指令資料夾只載入自己的 index.py；共用程式碼可放在同層模組。
                if filename == 'index.py':
                    rel_path = os.path.relpath(os.path.join(root, filename), BASE_DIR)
                    module_name = os.path.splitext(rel_path)[0].replace(os.sep, '.').replace('/', '.')
                    try:
                        await self.load_extension(module_name)
                        print(f'✅ 成功載入模組: {module_name}')
                    except Exception as e:
                        print(f'❌ 載入模組 {module_name} 失敗: {e}')
        
        # 4. 持久化視圖註冊 (重啟後恢復按鈕功能)
        try:
            from commands.訂單工具.index import (
                PaymentSelectView,
                AdminConfirmPaymentView,
                PlayerClaimView,
                PlayerCompleteView,
                ReviewView,
            )
            
            active_orders = database.get_active_orders()
            restored_count = 0
            for order in active_orders:
                try:
                    order_num = order['order_num']
                    status = order['status']
                    guild_id = order['guild_id']
                    if not guild_id:
                        print(f"⚠️ 訂單 {order_num} 缺少伺服器 ID，跳過按鈕恢復")
                        continue
                    
                    if status == 'PENDING':
                        if order['payment_method'] is None:
                            self.add_view(PaymentSelectView(order_num, guild_id))
                        else:
                            self.add_view(AdminConfirmPaymentView(order_num, guild_id))
                    elif status == 'WAITING':
                        self.add_view(PlayerClaimView(order_num, order['players_needed'], guild_id))
                    elif status == 'IN_PROGRESS':
                        self.add_view(PlayerCompleteView(order_num, guild_id))
                    restored_count += 1
                except Exception as order_err:
                    print(f"⚠️ 恢復訂單 {order.get('order_num', '未知')} 視圖失敗: {order_err}")
            
            print(f"✅ 已成功恢復 {restored_count}/{len(active_orders)} 個進行中訂單的按鈕功能")

            reviewable_orders = database.get_pending_reviews()
            review_restored_count = 0
            for order in reviewable_orders:
                self.add_view(
                    ReviewView(
                        order["order_num"],
                        order["guild_id"],
                        order["customer_id"],
                        order["type"],
                    )
                )
                review_restored_count += 1
            print(f"✅ 已成功恢復 {review_restored_count} 個待評價按鈕")
        except Exception as e:
            print(f"⚠️ 恢復訂單視圖時出錯: {e}")
        
        # 5. 同步斜線指令；Discord API 暫時無回應時不能阻塞機器人上線
        try:
            synced = await asyncio.wait_for(self.tree.sync(), timeout=30)
            print(f"✅ 已同步 {len(synced)} 個斜線指令")
        except asyncio.TimeoutError:
            print("⚠️ 斜線指令同步逾時，機器人將繼續嘗試連線")
        except discord.DiscordException as error:
            print(f"⚠️ 斜線指令同步失敗，機器人將繼續嘗試連線：{error}")

    async def on_connect(self):
        print("🔗 已連線至 Discord Gateway，等待完成登入...")

    async def on_ready(self):
        print(f"🔓 機器人已上線：{self.user}（ID: {self.user.id}）")

bot = MyBot()

if __name__ == "__main__":
    if not TOKEN:
        print("錯誤：請在 .env 中設定 DISCORD_TOKEN")
    else:
        bot.run(TOKEN)
