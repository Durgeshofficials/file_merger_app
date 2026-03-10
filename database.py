"""
database.py — models + ORM helpers.
Supports unlimited files per session, user-defined ordering, layout modes.
"""

import sqlite3
import os


def get_db(app):
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    return conn


def init_db(app):
    with app.app_context():
        conn = get_db(app)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS upload_session (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                session_token TEXT NOT NULL UNIQUE,
                layout_mode   TEXT DEFAULT 'auto_grid',
                output_pdf    TEXT,
                preview_img   TEXT,
                file_count    INTEGER DEFAULT 0,
                created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS uploaded_file (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL REFERENCES upload_session(id),
                sort_order INTEGER NOT NULL DEFAULT 0,
                filename   TEXT NOT NULL,
                filepath   TEXT NOT NULL,
                filetype   TEXT NOT NULL
            );
        """)
        conn.commit()
        conn.close()


def create_session(app, token, layout_mode="auto_grid"):
    conn = get_db(app)
    conn.execute(
        "INSERT INTO upload_session (session_token, layout_mode) VALUES (?, ?)",
        (token, layout_mode)
    )
    conn.commit()
    sid = conn.execute(
        "SELECT id FROM upload_session WHERE session_token=?", (token,)
    ).fetchone()["id"]
    conn.close()
    return sid


def save_file_record(app, session_id, sort_order, filename, filepath, filetype):
    conn = get_db(app)
    conn.execute(
        "INSERT INTO uploaded_file (session_id, sort_order, filename, filepath, filetype) "
        "VALUES (?, ?, ?, ?, ?)",
        (session_id, sort_order, filename, filepath, filetype)
    )
    conn.execute(
        "UPDATE upload_session SET file_count = file_count + 1 WHERE id = ?",
        (session_id,)
    )
    conn.commit()
    conn.close()


def reorder_files(app, session_id, ordered_file_ids):
    conn = get_db(app)
    for idx, fid in enumerate(ordered_file_ids):
        conn.execute(
            "UPDATE uploaded_file SET sort_order=? WHERE id=? AND session_id=?",
            (idx, fid, session_id)
        )
    conn.commit()
    conn.close()


def delete_file_record(app, file_id, session_id):
    conn = get_db(app)
    row = conn.execute(
        "SELECT filepath FROM uploaded_file WHERE id=? AND session_id=?",
        (file_id, session_id)
    ).fetchone()
    if row:
        try:
            os.remove(row["filepath"])
        except FileNotFoundError:
            pass
        conn.execute("DELETE FROM uploaded_file WHERE id=?", (file_id,))
        conn.execute(
            "UPDATE upload_session SET file_count = file_count - 1 WHERE id = ?",
            (session_id,)
        )
        conn.commit()
    conn.close()


def update_session_output(app, session_id, output_pdf, preview_img, layout_mode=None):
    conn = get_db(app)
    if layout_mode:
        conn.execute(
            "UPDATE upload_session SET output_pdf=?, preview_img=?, layout_mode=? WHERE id=?",
            (output_pdf, preview_img, layout_mode, session_id)
        )
    else:
        conn.execute(
            "UPDATE upload_session SET output_pdf=?, preview_img=? WHERE id=?",
            (output_pdf, preview_img, session_id)
        )
    conn.commit()
    conn.close()


def get_session(app, token):
    conn = get_db(app)
    row = conn.execute(
        "SELECT * FROM upload_session WHERE session_token=?", (token,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_session_by_id(app, session_id):
    conn = get_db(app)
    row = conn.execute(
        "SELECT * FROM upload_session WHERE id=?", (session_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_files_for_session(app, session_id):
    conn = get_db(app)
    rows = conn.execute(
        "SELECT * FROM uploaded_file WHERE session_id=? ORDER BY sort_order",
        (session_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
