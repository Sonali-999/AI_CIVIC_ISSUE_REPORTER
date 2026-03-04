# AI Civic Issue Reporter

## Setup Instructions

Run the following commands **in order**:

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app\iniAt_db.py
python set_admin_password.py
python -m app.gradio_app
```

---

## Run Application

To start the application after setup:

```bash
python -m app.gradio_app
```

---

## Project Directory Structure

```
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
```