import discord
from discord import app_commands
from discord.ext import commands
import database

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="取消訂單", description="【🔨管理員專用】 取消特定編號的訂單")
    @app_commands.guild_only()
    @app_commands.describe(order_num="請輸入 8 位訂單編號 (例如 ABCDE123)")
    async def cancel_order(self, interaction: discord.Interaction, order_num: str):
        # 權限檢查
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("你沒有權限使用此指令！", ephemeral=True)
            return
        
        # 獲取訂單資料 (自動轉大寫)
        order = database.get_order(order_num.upper(), interaction.guild_id)
        if not order:
            await interaction.response.send_message(f"找不到訂單編號 `{order_num}`！", ephemeral=True)
            return
        
        # 邏輯檢查：已結單訂單不可取消
        if order['status'] == 'COMPLETED':
            await interaction.response.send_message(f"❌ 訂單 `{order['order_num']}` 已經結單完成，無法取消！", ephemeral=True)
            return
        
        # 1. 更新資料庫狀態為已取消
        updated = database.update_order_status(
            order['order_num'],
            'CANCELLED',
            interaction.guild_id,
            expected_status=order['status'],
        )
        if not updated:
            await interaction.response.send_message(
                "訂單已被其他操作更新，請重新整理後再試。",
                ephemeral=True,
            )
            return
        database.export_orders_to_excel()
        
        # 2. 嘗試自動刪除接單頻道的舊訊息
        msg_id = order['dispatch_msg_id']
        chan_id = order['dispatch_channel_id']
        
        if msg_id and chan_id:
            try:
                channel = self.bot.get_channel(int(chan_id)) or await self.bot.fetch_channel(int(chan_id))
                if channel:
                    msg = await channel.fetch_message(int(msg_id))
                    await msg.delete()
            except Exception as e:
                print(f"自動刪除訊息失敗（可能已被手動刪除）：{e}")

        # 3. 發送公開取消通知
        cancel_embed = discord.Embed(title="🚫 頂單已取消", color=discord.Color.red())
        cancel_embed.description = (
            f"**訂單編號**\n`{order['order_num']}`\n\n"
            f"已由管理員 {interaction.user.mention} 取消，並已自動從接單頻道移除。"
        )
        await interaction.response.send_message(embed=cancel_embed)

async def setup(bot):
    await bot.add_cog(Admin(bot))
