# auth.py
# Wrappers to adapt db_utils for Gradio
from .db_utils import register_user, login_user  # <-- relative import

def register_user_wrapper(email, password):
    return register_user(email, password)

def login_user_wrapper(email, password):
    return login_user(email, password)
