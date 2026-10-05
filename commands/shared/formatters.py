def format_price(amount: float) -> str:
    """以一致的美元格式顯示金額。"""
    return f"${int(amount):,}" if amount == int(amount) else f"${amount:,.2f}"
