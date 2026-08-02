from dotenv import load_dotenv
load_dotenv()
import db
conn = db.get_connection()

total = conn.execute("SELECT COUNT(*) as c FROM guides").fetchone()
print("toplam rehber:", dict(total)["c"])

filled_tools = conn.execute("""
    SELECT COUNT(*) as c FROM guides
    WHERE related_tool_slugs IS NOT NULL AND related_tool_slugs != '' AND related_tool_slugs != '[]'
""").fetchone()
print("related_tool_slugs dolu:", dict(filled_tools)["c"])

filled_comp = conn.execute("""
    SELECT COUNT(*) as c FROM guides
    WHERE related_comparison_slugs IS NOT NULL AND related_comparison_slugs != '' AND related_comparison_slugs != '[]'
""").fetchone()
print("related_comparison_slugs dolu:", dict(filled_comp)["c"])

sample = conn.execute("SELECT title, related_tool_slugs, related_comparison_slugs FROM guides LIMIT 3").fetchall()
for s in sample:
    print(dict(s))

conn.close()
