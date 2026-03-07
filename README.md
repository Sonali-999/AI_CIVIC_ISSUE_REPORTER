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

## Running Demo Encryption
```bash
 python -m app.image_encryption
 python -m app.password_utils
 ```


## To see image_encryption keys in hexadecimal format
 
```bash
python -c "f=open('keys/aes_image_key.bin','rb'); print(f.read().hex())"
```

```mermaid
flowchart TD

A[User uploads image] --> B[Gradio saves file<br>Temp Directory<br>C:/Users/.../Temp/gradio]

B --> C[Copy file to uploads/photo.jpg<br>⚠ Temporary plaintext]

C --> D[Run encrypt_image()]

D --> E[Create encrypted file<br>uploads/photo.jpg.enc]

E --> F[Delete plaintext file<br>os.remove uploads/photo.jpg]

F --> G[Only encrypted file remains<br>uploads/photo.jpg.enc 🔒]

classDef user fill:#e3f2fd,stroke:#1e88e5,stroke-width:2px,color:#000
classDef process fill:#e8f5e9,stroke:#43a047,stroke-width:2px,color:#000
classDef warning fill:#fff3e0,stroke:#fb8c00,stroke-width:2px,color:#000
classDef secure fill:#e8eaf6,stroke:#5e35b1,stroke-width:2px,color:#000

class A user
class B,D,E,F process
class C warning
class G secure
```