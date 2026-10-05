import sqlite3

conn = sqlite3.connect('orders.db')
cursor = conn.cursor()

try:
    # 新增付款時間欄位
    cursor.execute('ALTER TABLE orders ADD COLUMN payment_time TEXT')
    print("✅ 已新增 payment_time 欄位")
except sqlite3.OperationalError:
    print("ℹ️ payment_time 欄位已存在")

try:
    # 新增結單時間欄位
    cursor.execute('ALTER TABLE orders ADD COLUMN completed_time TEXT')
    print("✅ 已新增 completed_time 欄位")
except sqlite3.OperationalError:
    print("ℹ️ completed_time 欄位已存在")

conn.commit()
conn.close()
print("🚀 資料庫修復完成！現在可以啟動機器人了。")
