from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from app import database


def test_existing_database_adds_diagnostics_without_losing_records(tmp_path, monkeypatch):
    path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE pdf_documents (id INTEGER PRIMARY KEY, filename TEXT, file_path TEXT, raw_text TEXT, summary TEXT, status TEXT, created_at DATETIME)"))
        connection.execute(text("INSERT INTO pdf_documents (id, filename, raw_text, summary, status) VALUES (1, 'saved.pdf', 'saved text', 'Error during extraction: failed', 'failed')"))
    monkeypatch.setattr(database, "engine", engine)
    database.initialize_database()
    database.initialize_database()
    with engine.connect() as connection:
        row = connection.execute(text("SELECT * FROM pdf_documents")).mappings().one()
        assert row["raw_text"] == "saved text" and row["filename"] == "saved.pdf"
        assert row["summary"] is None and row["error_message"].startswith("Error during")
    assert {"error_message", "warning_message"} <= {column["name"] for column in inspect(engine).get_columns("pdf_documents")}
    assert Path(str(path) + ".before_processing_diagnostics.bak").exists()
    engine.dispose()
