# AI Civic Issue Reporter

run these in order

venv\Scripts\activate
python app/init_db.py
pip install -r requirements.txt


run using-
python -m app.gradio_app

directory
AI_CIVIC_ISSUE_REPORTER/
│
├── app/
│   ├── uploads/        ← contains all uploaded images from runs
│   ├── ai_service.py
│   ├── auth.py
│   ├── db_utils.py
│   ├── gradio_app.py
│   ├── image_processor.py
│   └── init_db.py
│
├── sql/
│   └── init_schema.sql
│
├── tests/
├── venv/               ← virtual environment
├── .env                ← environment variables
├── requirements.txt
├── README.md
└── set_admin_password.py
