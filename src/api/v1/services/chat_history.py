import psycopg
import os

CONN = os.getenv("PG_CONNECTION_STRING")
CONN = CONN.replace("postgresql+psycopg", "postgresql")


def save_chat(session_id: str, query: str, answer: str, route: str):
    try:
        sql = """
        INSERT INTO chat_history (
            session_id, user_query, assistant_response, route
        )
        VALUES (%s, %s, %s, %s)
        """

        with psycopg.connect(CONN) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (session_id, query, answer, route))
            conn.commit()

    except Exception as e:
        print("[chat_history save error]", e)


def load_history(session_id: str):
    try:
        sql = """
        SELECT user_query, assistant_response, route
        FROM chat_history
        WHERE session_id = %s
        ORDER BY created_at ASC
        """

        with psycopg.connect(CONN) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (session_id,))
                return cur.fetchall()

    except Exception as e:
        print("[chat_history load error]", e)
        return []

