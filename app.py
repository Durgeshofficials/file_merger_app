"""
File Merger App — Flask equivalent of the Django file_merger project.
Mirrors Django's MTV pattern:
  models   → models.py (SQLite via sqlite3)
  forms    → forms.py  (WTForms-style validation in forms.py)
  views    → views.py  (blueprints)
  urls     → url routing in this file
"""

from flask import Flask
from config import Config
from database import init_db

app = Flask(__name__)
app.config.from_object(Config)

# Initialise the SQLite database (mirrors Django's migrate)
init_db(app)

# Register blueprint (mirrors Django's include('file_merger.urls'))
from views import merger_bp
app.register_blueprint(merger_bp)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
