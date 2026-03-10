"""
views.py — 4-step wizard.
FIX: Store only filename in DB (not full abs path). Reconstruct abs paths at runtime.
This fixes Windows backslash path issues in Jinja templates and cross-platform usage.
"""

import os
import json
import secrets
import threading
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, send_from_directory, current_app, abort, jsonify
)
from werkzeug.utils import secure_filename

from forms import validate_upload_form
from database import (
    create_session, save_file_record, reorder_files, delete_file_record,
    update_session_output, get_session, get_files_for_session, get_db
)
from pdf_processor import build_merged_pdf

merger_bp = Blueprint("merger", __name__)

_processing_status = {}
_status_lock = threading.Lock()


def _set_status(token, **kwargs):
    with _status_lock:
        _processing_status[token] = kwargs


def _get_status(token):
    with _status_lock:
        return _processing_status.get(token, {"state": "unknown", "progress": 0, "message": ""})


def _detect_filetype(filename):
    ext = filename.rsplit(".", 1)[-1].lower()
    return "pdf" if ext == "pdf" else "image"


def _abs_upload_path(app, filename):
    """Reconstruct absolute path from stored filename."""
    return os.path.join(app.config["UPLOAD_FOLDER"], filename)


def _enrich_files(app, files):
    """Add abs_filepath to each file record (reconstructed from filename)."""
    for f in files:
        f["abs_filepath"] = _abs_upload_path(app, f["filepath"])
    return files


# ── Step 1: Upload ────────────────────────────────────────────────────────────

@merger_bp.route("/", methods=["GET"])
def upload_page():
    return render_template("upload.html")


@merger_bp.route("/upload", methods=["POST"])
def upload_files():
    files_list = request.files.getlist("files")
    valid_files, errors = validate_upload_form(files_list)

    if errors:
        return render_template("upload.html", errors=errors)

    token      = secrets.token_urlsafe(16)
    session_id = create_session(current_app._get_current_object(), token)

    upload_dir = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_dir, exist_ok=True)

    for idx, file_storage in valid_files:
        original_name = secure_filename(file_storage.filename)
        # Store only the unique filename (no abs path) — cross-platform safe
        unique_name   = f"{token}_{idx:03d}_{original_name}"
        abs_path      = os.path.join(upload_dir, unique_name)
        file_storage.save(abs_path)
        filetype = _detect_filetype(original_name)
        save_file_record(
            current_app._get_current_object(),
            session_id, idx,
            original_name,   # display name
            unique_name,     # stored filename (relative, no abs path)
            filetype
        )

    return redirect(url_for("merger.arrange_page", token=token))


# ── Step 2: Arrange ───────────────────────────────────────────────────────────

@merger_bp.route("/arrange/<token>", methods=["GET"])
def arrange_page(token):
    app = current_app._get_current_object()
    session = get_session(app, token)
    if not session:
        abort(404)
    files = get_files_for_session(app, session["id"])
    return render_template("arrange.html", session=session, files=files, token=token)


@merger_bp.route("/arrange/<token>/remove/<int:file_id>", methods=["POST"])
def remove_file(token, file_id):
    app = current_app._get_current_object()
    session = get_session(app, token)
    if not session:
        abort(404)
    # delete_file_record needs abs path — reconstruct it
    files = get_files_for_session(app, session["id"])
    target = next((f for f in files if f["id"] == file_id), None)
    if target:
        abs_path = _abs_upload_path(app, target["filepath"])
        try:
            os.remove(abs_path)
        except FileNotFoundError:
            pass
        conn = get_db(app)
        conn.execute("DELETE FROM uploaded_file WHERE id=?", (file_id,))
        conn.execute("UPDATE upload_session SET file_count = file_count - 1 WHERE id=?",
                     (session["id"],))
        conn.commit()
        conn.close()
    return jsonify({"ok": True})


@merger_bp.route("/arrange/<token>/reorder", methods=["POST"])
def reorder(token):
    app = current_app._get_current_object()
    session = get_session(app, token)
    if not session:
        abort(404)
    data = request.get_json()
    ordered_ids = [int(x) for x in data.get("order", [])]
    reorder_files(app, session["id"], ordered_ids)
    return jsonify({"ok": True})


@merger_bp.route("/arrange/<token>/process", methods=["POST"])
def start_processing(token):
    app = current_app._get_current_object()
    session = get_session(app, token)
    if not session:
        abort(404)

    layout_mode = request.form.get("layout_mode", "auto_grid")
    _set_status(token, state="queued", progress=0, message="Starting…")

    flask_app = current_app._get_current_object()

    def _run():
        with flask_app.app_context():
            try:
                _set_status(token, state="processing", progress=10,
                            message="Loading files…")
                files = get_files_for_session(flask_app, session["id"])
                if not files:
                    _set_status(token, state="error", progress=0,
                                message="No files found.")
                    return

                _set_status(token, state="processing", progress=30,
                            message="Converting pages to images…")

                # Reconstruct abs paths for processor
                upload_dir = flask_app.config["UPLOAD_FOLDER"]
                for f in files:
                    f["abs_filepath"] = os.path.join(upload_dir, f["filepath"])

                output_dir   = flask_app.config["OUTPUT_FOLDER"]
                os.makedirs(output_dir, exist_ok=True)
                pdf_name     = f"{token}_merged.pdf"
                preview_name = f"{token}_preview.png"
                pdf_path     = os.path.join(output_dir, pdf_name)
                preview_path = os.path.join(output_dir, preview_name)

                _set_status(token, state="processing", progress=55,
                            message="Composing A4 layout…")

                # Pass abs_filepath as filepath to processor
                proc_records = [
                    {"slot": f["sort_order"], "filepath": f["abs_filepath"],
                     "filetype": f["filetype"], "filename": f["filename"]}
                    for f in files
                ]
                pages = build_merged_pdf(proc_records, pdf_path, preview_path, layout_mode)

                _set_status(token, state="processing", progress=85,
                            message="Writing PDF…")

                update_session_output(
                    flask_app, session["id"],
                    os.path.join("outputs", pdf_name),
                    os.path.join("outputs", preview_name),
                    layout_mode
                )

                _set_status(token, state="done", progress=100,
                            message=f"Done! {pages} page(s) generated.",
                            redirect=f"/preview/{token}")
            except Exception as e:
                import traceback
                _set_status(token, state="error", progress=0,
                            message=str(e) + "\n" + traceback.format_exc())

    threading.Thread(target=_run, daemon=True).start()
    return redirect(url_for("merger.processing_page", token=token))


# ── Step 3: Processing / Progress ────────────────────────────────────────────

@merger_bp.route("/processing/<token>")
def processing_page(token):
    session = get_session(current_app._get_current_object(), token)
    if not session:
        abort(404)
    return render_template("processing.html", token=token)


@merger_bp.route("/status/<token>")
def status(token):
    return jsonify(_get_status(token))


# ── Step 4: Preview + Download ────────────────────────────────────────────────

@merger_bp.route("/preview/<token>")
def preview_page(token):
    app = current_app._get_current_object()
    session = get_session(app, token)
    if not session:
        abort(404)
    files = get_files_for_session(app, session["id"])

    # Build preview URL — use forward slashes always (URL safe)
    preview_url = None
    if session.get("preview_img"):
        # Normalise to forward slashes for URL
        rel = session["preview_img"].replace("\\", "/")
        preview_url = f"/media/{rel}"

    download_url = url_for("merger.download_pdf", token=token)
    return render_template("preview.html", session=session, files=files,
                           preview_url=preview_url, download_url=download_url,
                           token=token)


@merger_bp.route("/download/<token>")
def download_pdf(token):
    """Force-download the merged PDF."""
    app = current_app._get_current_object()
    session = get_session(app, token)
    if not session or not session.get("output_pdf"):
        abort(404)
    rel = session["output_pdf"].replace("\\", "/")
    pdf_abs = os.path.join(app.config["MEDIA_FOLDER"], rel)
    directory, filename = os.path.split(pdf_abs)
    return send_from_directory(directory, filename,
                               as_attachment=True,
                               download_name="merged_a4.pdf")


@merger_bp.route("/view-pdf/<token>")
def view_pdf_inline(token):
    """Serve merged PDF inline (no download) — for <iframe> embedding."""
    from flask import make_response
    app = current_app._get_current_object()
    session = get_session(app, token)
    if not session or not session.get("output_pdf"):
        abort(404)
    rel = session["output_pdf"].replace("\\", "/")
    pdf_abs = os.path.join(app.config["MEDIA_FOLDER"], rel)
    directory, filename = os.path.split(pdf_abs)
    response = send_from_directory(directory, filename, as_attachment=False)
    response.headers["Content-Disposition"] = f"inline; filename={filename}"
    response.headers["Content-Type"] = "application/pdf"
    # Allow iframe embedding from same origin
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    return response


@merger_bp.route("/view-file/<token>/<int:file_id>")
def view_file_inline(token, file_id):
    """Serve an individual uploaded file inline for preview."""
    from flask import make_response
    import mimetypes
    app = current_app._get_current_object()
    session = get_session(app, token)
    if not session:
        abort(404)
    files = get_files_for_session(app, session["id"])
    target = next((f for f in files if f["id"] == file_id), None)
    if not target:
        abort(404)
    abs_path = os.path.join(app.config["UPLOAD_FOLDER"], target["filepath"])
    directory, filename = os.path.split(abs_path)
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    response = send_from_directory(directory, filename, as_attachment=False)
    response.headers["Content-Disposition"] = f"inline; filename={target['filename']}"
    response.headers["Content-Type"] = mime
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    return response


@merger_bp.route("/media/<path:filepath>")
def serve_media(filepath):
    """Serve any file under media/. filepath is relative to MEDIA_FOLDER."""
    media_dir = current_app.config["MEDIA_FOLDER"]
    return send_from_directory(media_dir, filepath)
