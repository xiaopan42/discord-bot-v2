"""集中管理機器人的環境設定。"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

TOKEN = os.getenv("DISCORD_TOKEN")
DISPATCH_CHANNEL_ID = os.getenv("DISPATCH_CHANNEL_ID")
LOG_CHANNEL_ID = os.getenv("LOG_CHANNEL_ID")

SHIPPING_LOG_CHANNEL_ID = 1540115127179804765
STOCK_PRODUCTS = {
    "100m幣號": os.getenv("100M_CHANNEL_ID"),
    "200m幣號": os.getenv("200M_CHANNEL_ID"),
}


def get_stock_channel_id(product_name: str) -> int:
    """取得商品庫存頻道 ID，設定缺失時給出明確錯誤。"""
    value = STOCK_PRODUCTS[product_name]
    if not value:
        raise ValueError(f"尚未設定 {product_name} 的庫存頻道 ID")
    return int(value)
