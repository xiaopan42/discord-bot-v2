import discord
from discord import app_commands
from discord.ext import commands


class Say(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="say", description="【🔨管理員專用】 發送一般訊息或自訂 Embed")
    @app_commands.describe(
        type="選擇要發送 message 或 embed",
    )
    @app_commands.choices(
        type=[
            app_commands.Choice(name="Message", value="message"),
            app_commands.Choice(name="Embed", value="embed"),
        ]
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def say(
        self,
        interaction: discord.Interaction,
        type: app_commands.Choice[str],
    ):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("你沒有權限使用此指令。", ephemeral=True)
            return

        if type.value == "embed":
            await interaction.response.send_modal(EmbedGeneratorModal())
            return

        await interaction.response.send_modal(MessageGeneratorModal())


class MessageGeneratorModal(discord.ui.Modal, title="發送 Message"):
    message = discord.ui.TextInput(
        label="訊息內容",
        placeholder="請輸入訊息（支援 Discord Markdown、提及與換行）",
        style=discord.TextStyle.paragraph,
        max_length=2000,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.channel.send(self.message.value.replace("\\n", "\n"))
        await interaction.response.send_message("訊息已成功發送！", ephemeral=True)


class EmbedGeneratorModal(discord.ui.Modal, title="自定義 Embed 文字"):
    embed_title = discord.ui.TextInput(label="標題", placeholder="請輸入公告標題", required=True)
    description = discord.ui.TextInput(
        label="內容",
        placeholder="請輸入公告內容（支援 Discord Markdown 語法）",
        style=discord.TextStyle.paragraph,
        required=True,
    )
    color_hex = discord.ui.TextInput(
        label="框線顏色（Hex Code）",
        placeholder="例如：#ff0000 或 #00bfff",
        default="#00bfff",
        required=False,
    )
    image_url = discord.ui.TextInput(label="大圖片網址（選填）", placeholder="https://...", required=False)
    thumbnail_url = discord.ui.TextInput(label="右上角小圖網址（選填）", placeholder="https://...", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            color = int(self.color_hex.value.strip().lstrip("#"), 16)
        except ValueError:
            color = 0x00BFFF

        embed = discord.Embed(
            title=self.embed_title.value,
            description=self.description.value,
            color=color,
        )
        if self.image_url.value:
            embed.set_image(url=self.image_url.value)
        if self.thumbnail_url.value:
            embed.set_thumbnail(url=self.thumbnail_url.value)

        await interaction.channel.send(embed=embed)
        await interaction.response.send_message("Embed已成功發送！", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Say(bot))
