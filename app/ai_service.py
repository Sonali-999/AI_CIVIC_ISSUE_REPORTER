# ai_service.py
import os
from .db_utils import register_user, login_user  # relative import if needed
from groq import Groq

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

SYSTEM_PROMPT = (
    "You are an AI Civic Issue Detector. When given an image and optional user text, "
    "produce exactly these fields in plain text, each on its own line: \n"
    "Title: <short title>\nCategory: <one-word category like Garbage, Streetlight, Dead Animal, Sewage, Pothole, Waterlogging>\n"
    "Department: <municipal department>\nDescription: <short paragraph about what is wrong and how it impacts hygiene/safety/environment>\n"
    "Keep answers concise and use simple language."
)

def analyze_image_with_query(query_text, encoded_image, model="meta-llama/llama-4-scout-17b-16e-instruct"):
    client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else Groq()

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": f"{SYSTEM_PROMPT}\nUser note: {query_text}"},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded_image}"}}  
            ],
        }
    ]

    chat_completion = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=300,
    )

    resp = chat_completion.choices[0].message.content
    if isinstance(resp, list):
        out = "".join([c.get("text", "") for c in resp if isinstance(c, dict)])
    else:
        out = str(resp)
    return out
