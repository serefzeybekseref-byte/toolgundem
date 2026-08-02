from dotenv import load_dotenv
load_dotenv()
import db
conn = db.get_connection()
filled = conn.execute("""
    SELECT COUNT(*) as c FROM guides
    WHERE related_comparison_slugs IS NOT NULL AND related_comparison_slugs != ''
""").fetchone()
print("related_comparison_slugs dolu:", dict(filled)["c"], "/ 74")
conn.close()
