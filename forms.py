"""
forms.py — validates N uploaded files (no fixed limit).
"""

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "pdf"}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def validate_upload_form(files_list) -> tuple:
    """
    files_list: list of FileStorage objects from request.files.getlist('files')
    Returns (valid_files, errors)
    valid_files: list of (index, FileStorage)
    """
    errors = []
    valid_files = []

    for idx, f in enumerate(files_list):
        if f and f.filename:
            if not allowed_file(f.filename):
                errors.append(f"'{f.filename}' — only JPG, PNG, PDF are allowed.")
            else:
                valid_files.append((idx, f))

    if not valid_files:
        errors.append("Please upload at least one file.")

    return valid_files, errors
