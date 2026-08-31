import re

with open("iha_producer.py", "r", encoding="utf-8") as f:
    content = f.read()

# Emojileri temizle
content = re.sub(r'[\U00010000-\U0010ffff]', '', content) # Removes most emojis
content = content.replace("🚨 ", "").replace("🛑 ", "").replace("🛬 ", "").replace("⚙️ ", "").replace("🕹️ ", "")
content = content.replace("🚀 ", "").replace("🛫 ", "").replace("✈️ ", "").replace("⚠️ ", "").replace("✅ ", "")

# durable=True'yu False yap
content = content.replace("durable=True", "durable=False")

with open("iha_producer.py", "w", encoding="utf-8") as f:
    f.write(content)

with open("app.py", "r", encoding="utf-8") as f:
    app_content = f.read()
app_content = app_content.replace("durable=True", "durable=False")
with open("app.py", "w", encoding="utf-8") as f:
    f.write(app_content)

print("Fix completed.")
