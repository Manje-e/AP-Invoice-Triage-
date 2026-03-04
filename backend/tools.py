import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def get_connection():
    return psycopg2.connect(DATABASE_URL)

def execute_sql(query: str) -> dict:
    """
    Executes a SELECT SQL query against the Supabase database.
    Returns a dict with 'columns', 'rows', and 'row_count'.
    Only SELECT queries are allowed.
    """
    # Guardrail — only allow SELECT
    clean_query = query.strip().upper()
    forbidden = ["DELETE", "UPDATE", "INSERT", "DROP", "ALTER", "TRUNCATE", "CREATE"]
    for keyword in forbidden:
        if clean_query.startswith(keyword) or f" {keyword} " in clean_query:
            return {
                "error": f"Query blocked — {keyword} statements are not allowed. Only SELECT is permitted.",
                "columns": [],
                "rows": [],
                "row_count": 0
            }

    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query)
            rows = cur.fetchall()
            columns = list(rows[0].keys()) if rows else []
            rows_list = [dict(row) for row in rows]

            # Convert any non-serializable types (dates, decimals)
            import json
            from datetime import date, datetime
            from decimal import Decimal

            def serialize(obj):
                if isinstance(obj, (date, datetime)):
                    return obj.isoformat()
                if isinstance(obj, Decimal):
                    return float(obj)
                return str(obj)

            rows_serialized = json.loads(
                json.dumps(rows_list, default=serialize)
            )

            return {
                "columns": columns,
                "rows": rows_serialized,
                "row_count": len(rows_serialized)
            }

    except Exception as e:
        return {
            "error": str(e),
            "columns": [],
            "rows": [],
            "row_count": 0
        }
    finally:
        if conn:
            conn.close()
