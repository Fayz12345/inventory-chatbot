import os
os.environ["CHAT_LOG_DB_PATH"] = "/tmp/test_chat_log_unit.db"
if os.path.exists("/tmp/test_chat_log_unit.db"):
    os.remove("/tmp/test_chat_log_unit.db")
import chat_log


def test_log_and_recent_roundtrip():
    chat_log.init_db()
    chat_log.log_query(username="u", question="q1", sql="SELECT 1",
                       ok=True, row_count=3, retries=1, latency_ms=250,
                       input_tokens=100, output_tokens=20)
    rows = chat_log.recent(10)
    assert rows[0]['question'] == "q1"
    assert rows[0]['ok'] == 1 and rows[0]['retries'] == 1
    assert rows[0]['row_count'] == 3


def test_log_records_failures():
    chat_log.init_db()
    chat_log.log_query(username="u", question="bad", ok=False, error="boom")
    assert any(r['error'] == "boom" for r in chat_log.recent(10))
