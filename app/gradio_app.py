# gradio_app.py
import os
import gradio as gr
import shutil
from dotenv import load_dotenv

from .auth import register_user_wrapper, login_user_wrapper
from .db_utils import save_complaint, get_complaints_by_department
from .image_processor import encode_image
from .ai_service import analyze_image_with_query

# ---------------- Load environment ----------------
load_dotenv()

# ---------------- System Prompt ----------------
system_prompt = (
    "You are an AI civic issue detector. Analyze the uploaded image, identify the type of problem "
    "(e.g., garbage, pothole, dead animal, broken streetlight, sewage), determine the relevant municipal department "
    "(Sanitation, Roads, Electricity, etc.), generate a short title and description including impact on public hygiene, safety, and environment. "
    "Output should be concise and ready to autofill the complaint form."
)

# ---------------- Custom CSS for Modern Green Civic UI ----------------
custom_css = """
/* Green Civic Theme - Modern & Clean */
:root {
    --primary-green: #4caf50;
    --primary-dark: #388e3c;
    --primary-light: #81c784;
    --accent-green: #66bb6a;
    --bg-cream: #f9fdf9;
    --bg-light: #e8f5e9;
    --card-bg: #ffffff;
    --text-primary: #2c3e2c;
    --text-secondary: #5a7a5a;
    --text-muted: #7a9a7a;
    --border-soft: #c8e6c9;
    --shadow-sm: 0 2px 8px rgba(76, 175, 80, 0.08);
    --shadow-md: 0 4px 16px rgba(76, 175, 80, 0.12);
    --shadow-lg: 0 8px 32px rgba(76, 175, 80, 0.15);
    --border-radius: 12px;
    --transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

/* Global Container */
.gradio-container {
    font-family: 'Inter', 'SF Pro Display', -apple-system, BlinkMacSystemFont, sans-serif !important;
    background: var(--bg-cream) !important;
    min-height: 100vh;
}

/* Top Header Bar - Sticky */
#header {
    position: sticky !important;
    top: 0 !important;
    z-index: 100 !important;
    background: linear-gradient(135deg, var(--primary-green), var(--primary-dark)) !important;
    color: white !important;
    padding: 1.25rem 2rem !important;
    box-shadow: var(--shadow-md) !important;
    display: flex !important;
    justify-content: space-between !important;
    align-items: center !important;
}

#header h1 {
    font-size: 1.75rem !important;
    font-weight: 700 !important;
    margin: 0 !important;
    letter-spacing: -0.5px !important;
}

/* User Info Badge in Header */
.user-badge {
    background: rgba(255, 255, 255, 0.2) !important;
    backdrop-filter: blur(10px) !important;
    padding: 0.5rem 1.25rem !important;
    border-radius: 24px !important;
    font-size: 0.9rem !important;
    font-weight: 600 !important;
    display: flex !important;
    align-items: center !important;
    gap: 0.5rem !important;
}

/* Tab Navigation - Side by Side Centered */
.tab-nav {
    display: flex !important;
    justify-content: center !important;
    align-items: center !important;
    gap: 1rem !important;
    padding: 1.5rem 2rem !important;
    margin: 2rem auto !important;
    background: var(--card-bg) !important;
    border-radius: 16px !important;
    box-shadow: var(--shadow-sm) !important;
    max-width: 800px !important;
}

.tab-nav button {
    background: var(--bg-light) !important;
    border: 2px solid transparent !important;
    border-radius: var(--border-radius) !important;
    padding: 0.875rem 2rem !important;
    font-weight: 600 !important;
    color: var(--text-primary) !important;
    transition: var(--transition) !important;
    font-size: 0.95rem !important;
    cursor: pointer !important;
}

.tab-nav button.selected {
    background: var(--primary-green) !important;
    color: white !important;
    box-shadow: 0 4px 12px rgba(76, 175, 80, 0.25) !important;
}

.tab-nav button:hover:not(.selected) {
    background: var(--primary-light) !important;
    color: white !important;
    transform: translateY(-2px) !important;
}

/* Auth Form Container - Compact Side by Side */
.auth-container {
    max-width: 900px !important;
    margin: 2rem auto !important;
    background: var(--card-bg) !important;
    border-radius: 20px !important;
    padding: 2.5rem !important;
    box-shadow: var(--shadow-md) !important;
}

.auth-title {
    text-align: center !important;
    font-size: 1.5rem !important;
    font-weight: 700 !important;
    color: var(--text-primary) !important;
    margin-bottom: 2rem !important;
}

/* Card Blocks - Neumorphism */
.block {
    background: var(--card-bg) !important;
    border-radius: var(--border-radius) !important;
    box-shadow: 
        8px 8px 16px rgba(76, 175, 80, 0.08),
        -8px -8px 16px rgba(255, 255, 255, 0.9) !important;
    border: 1px solid var(--border-soft) !important;
    padding: 1.5rem !important;
    margin-bottom: 1.5rem !important;
    transition: var(--transition) !important;
}

.block:hover {
    box-shadow: 
        12px 12px 24px rgba(76, 175, 80, 0.12),
        -12px -12px 24px rgba(255, 255, 255, 1) !important;
}

/* Input Fields - Clean & Modern */
input, textarea, select {
    border: 2px solid var(--border-soft) !important;
    border-radius: var(--border-radius) !important;
    padding: 0.875rem 1rem !important;
    font-size: 0.95rem !important;
    transition: var(--transition) !important;
    background: var(--card-bg) !important;
    color: var(--text-primary) !important;
    font-weight: 500 !important;
}

input:focus, textarea:focus, select:focus {
    border-color: var(--primary-green) !important;
    box-shadow: 0 0 0 3px rgba(76, 175, 80, 0.1) !important;
    outline: none !important;
}

input::placeholder, textarea::placeholder {
    color: var(--text-muted) !important;
    opacity: 0.7 !important;
}

/* Buttons - Soft Accent */
button {
    background: var(--primary-green) !important;
    color: white !important;
    border: none !important;
    border-radius: var(--border-radius) !important;
    padding: 0.875rem 1.75rem !important;
    font-weight: 600 !important;
    font-size: 0.95rem !important;
    cursor: pointer !important;
    transition: var(--transition) !important;
    box-shadow: var(--shadow-sm) !important;
}

button:hover {
    background: var(--primary-dark) !important;
    transform: translateY(-2px) !important;
    box-shadow: var(--shadow-md) !important;
}

.secondary-btn {
    background: var(--accent-green) !important;
}

.secondary-btn:hover {
    background: var(--primary-light) !important;
}

.signout-btn {
    background: rgba(244, 67, 54, 0.9) !important;
    padding: 0.5rem 1.25rem !important;
    font-size: 0.85rem !important;
}

.signout-btn:hover {
    background: rgba(211, 47, 47, 1) !important;
}

/* Image Upload Area */
.image-upload {
    border: 3px dashed var(--border-soft) !important;
    border-radius: var(--border-radius) !important;
    padding: 2.5rem !important;
    text-align: center !important;
    background: var(--bg-light) !important;
    transition: var(--transition) !important;
    cursor: pointer !important;
}

.image-upload:hover {
    border-color: var(--primary-green) !important;
    background: rgba(129, 199, 132, 0.1) !important;
}

/* Status Messages */
.status-success {
    background: linear-gradient(135deg, var(--primary-green), var(--primary-dark)) !important;
    color: white !important;
    padding: 1rem 1.5rem !important;
    border-radius: var(--border-radius) !important;
    margin: 1rem 0 !important;
    font-weight: 600 !important;
    text-align: center !important;
    animation: slideIn 0.4s ease !important;
    box-shadow: var(--shadow-sm) !important;
}

.status-error {
    background: linear-gradient(135deg, #ef5350, #e53935) !important;
    color: white !important;
    padding: 1rem 1.5rem !important;
    border-radius: var(--border-radius) !important;
    margin: 1rem 0 !important;
    font-weight: 600 !important;
    text-align: center !important;
    animation: slideIn 0.4s ease !important;
    box-shadow: var(--shadow-sm) !important;
}

/* Animations */
@keyframes slideIn {
    from { opacity: 0; transform: translateY(-10px); }
    to { opacity: 1; transform: translateY(0); }
}

@keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
}

/* Complaint Cards - Clean Design */
.complaint-card {
    background: var(--card-bg) !important;
    border-radius: 16px !important;
    padding: 1.5rem !important;
    margin-bottom: 1.5rem !important;
    box-shadow: var(--shadow-md) !important;
    border: 1px solid var(--border-soft) !important;
    transition: var(--transition) !important;
    position: relative !important;
}

.complaint-card::before {
    content: '' !important;
    position: absolute !important;
    top: 0 !important;
    left: 0 !important;
    right: 0 !important;
    height: 3px !important;
    background: linear-gradient(90deg, var(--primary-green), var(--primary-light)) !important;
    border-radius: 16px 16px 0 0 !important;
}

.complaint-card:hover {
    transform: translateY(-4px) !important;
    box-shadow: var(--shadow-lg) !important;
}

/* Department Headers */
.dept-header {
    background: linear-gradient(135deg, var(--primary-green), var(--primary-dark)) !important;
    color: white !important;
    padding: 1.25rem 2rem !important;
    border-radius: var(--border-radius) !important;
    margin: 2rem 0 1rem 0 !important;
    font-size: 1.25rem !important;
    font-weight: 700 !important;
    text-align: center !important;
    box-shadow: var(--shadow-sm) !important;
    letter-spacing: 0.5px !important;
}

/* Info Badges */
.info-badge {
    background: var(--bg-light) !important;
    padding: 0.75rem 1rem !important;
    border-radius: var(--border-radius) !important;
    border: 1px solid var(--border-soft) !important;
}

.info-badge-label {
    font-size: 0.75rem !important;
    color: var(--text-muted) !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.5px !important;
    margin-bottom: 0.25rem !important;
}

.info-badge-value {
    font-size: 1rem !important;
    color: var(--text-primary) !important;
    font-weight: 600 !important;
}

/* Loading Overlay */
.loading-overlay {
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    right: 0 !important;
    bottom: 0 !important;
    background: rgba(249, 253, 249, 0.95) !important;
    backdrop-filter: blur(8px) !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    z-index: 1000 !important;
}

.loading-spinner {
    width: 60px !important;
    height: 60px !important;
    border: 4px solid var(--bg-light) !important;
    border-top-color: var(--primary-green) !important;
    border-radius: 50% !important;
    animation: spin 1s linear infinite !important;
}

@keyframes spin {
    to { transform: rotate(360deg); }
}

/* Responsive Design */
@media (max-width: 768px) {
    #header {
        flex-direction: column !important;
        gap: 1rem !important;
        padding: 1rem !important;
    }
    
    #header h1 {
        font-size: 1.5rem !important;
    }
    
    .auth-container {
        padding: 1.5rem !important;
        margin: 1rem !important;
    }
    
    .tab-nav {
        flex-direction: column !important;
        gap: 0.75rem !important;
        padding: 1rem !important;
    }
    
    .tab-nav button {
        width: 100% !important;
    }
    
    button {
        padding: 0.75rem 1.25rem !important;
        font-size: 0.9rem !important;
    }
}

/* Section Headers */
.section-title {
    font-size: 1.1rem !important;
    font-weight: 600 !important;
    color: var(--text-primary) !important;
    margin-bottom: 1rem !important;
    padding-bottom: 0.5rem !important;
    border-bottom: 2px solid var(--border-soft) !important;
}

/* Image Display Styling */
.image-display-card {
    border-radius: 12px !important;
    overflow: hidden !important;
    box-shadow: var(--shadow-md) !important;
    margin-bottom: 1rem !important;
}

.image-display-card img {
    width: 100% !important;
    height: auto !important;
    display: block !important;
}
"""

# ---------------- Authentication Functions ----------------
def signup(email, password, state):
    result = register_user_wrapper(email, password)
    if "success" in result.get("status", "").lower():
        return f'<div class="status-success">✨ {result["status"]} Welcome to the platform!</div>', state
    else:
        return f'<div class="status-error">❌ {result.get("status", "Error")}</div>', state

def login(email, password, state):
    result = login_user_wrapper(email, password)
    if result.get("status") == "success":
        state["uid"] = result["user_id"]
        state["email"] = email
        state["role"] = result.get("role", "citizen")
        header_html = f'''
        <div id="header">
            <h1>🌿 Green Civic Reporter</h1>
            <div style="display: flex; gap: 1rem; align-items: center;">
                <div class="user-badge">
                     {email} | {result.get("role", "citizen").title()}
                </div>
            </div>
        </div>
        '''
        return f'<div class="status-success"> Welcome back, {email}!</div>', state, header_html
    else:
        state["uid"] = None
        state["email"] = None
        state["role"] = None
        default_header = '<div id="header"><h1>🌿 Green Civic Reporter</h1></div>'
        return f'<div class="status-error">Invalid credentials. Please try again.</div>', state, default_header

def signout(state):
    state["uid"] = None
    state["email"] = None
    state["role"] = None
    default_header = '<div id="header"><h1>🌿 Green Civic Reporter</h1></div>'
    return '<div class="status-success"> Successfully signed out!</div>', state, default_header

# ---------------- AI Complaint Processing ----------------
def parse_ai_output(ai_output):
    title = category = department = description = "N/A"
    try:
        for line in ai_output.split("\n"):
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip().lower()
            value = value.strip()
            if "title" in key:
                title = value
            elif "category" in key:
                category = value
            elif "department" in key:
                department = value
            elif "description" in key:
                description = value
    except Exception as e:
        print("Error parsing AI output:", e)
    return title, category, department, description

def format_citizen_ai_output(title, category, department, description):
    dept_icons = {
        "Sanitation": "🗑️",
        "Roads": "🛣️",
        "Electricity": "⚡",
        "Water": "💧"
    }
    
    html_content = f"""
    <div class="complaint-card" style="animation: fadeIn 0.5s ease;">
        <div style="display: grid; gap: 1rem;">
            <div class="info-badge">
                <div class="info-badge-label"> Title</div>
                <div class="info-badge-value" style="font-size: 1.2rem;">{title}</div>
            </div>
            
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
                <div class="info-badge">
                    <div class="info-badge-label"> Category</div>
                    <div class="info-badge-value">{category}</div>
                </div>
                
                <div class="info-badge">
                    <div class="info-badge-label">{dept_icons.get(department, '🏢')} Department</div>
                    <div class="info-badge-value">{department}</div>
                </div>
            </div>
            
            <div class="info-badge">
                <div class="info-badge-label">📝 Description</div>
                <div style="color: var(--text-secondary); line-height: 1.6; margin-top: 0.5rem;">{description}</div>
            </div>
        </div>
        
        <div style="text-align: center; margin-top: 1.5rem; padding: 1rem; background: var(--bg-light); border-radius: 12px; color: var(--primary-dark); font-weight: 600;">
             Complaint submitted successfully! We'll process it shortly.
        </div>
    </div>
    """
    return html_content

def process_complaint(image_path, user_msg, state):
    if not state.get("uid"):
        return '<div class="status-error"> Please log in first to submit a complaint.</div>', None

    if not image_path:
        return '<div class="status-error">Please upload an image of the issue.</div>', None

    try:
        ai_output = analyze_image_with_query(
            query_text=f"{system_prompt} {user_msg}",
            encoded_image=encode_image(image_path),
            model="meta-llama/llama-4-scout-17b-16e-instruct"
        )
        title, category, department, description = parse_ai_output(ai_output)
        save_complaint(state["uid"], title, category, department, description, image_path)
        html_content = format_citizen_ai_output(title, category, department, description)

        # Return HTML content and image path for Gradio to display
        return html_content, image_path
    except Exception as e:
        return f'<div class="status-error"> Error processing complaint: {str(e)}</div>', None

# ---------------- Admin Dashboard ----------------
def get_admin_complaints_html(state):
    if state.get("role") != "admin":
        return '<div class="status-error">🚫 Admin access required</div>', []

    departments = ["Sanitation", "Roads", "Electricity", "Water"]
    dept_icons = {"Sanitation": "🗑️", "Roads": "🛣️", "Electricity": "⚡", "Water": "💧"}
    
    html_content = '<div style="animation: fadeIn 0.6s ease;">'
    image_paths = []

    for dept in departments:
        rows = get_complaints_by_department(dept)
        if not rows:
            continue

        html_content += f"""
        <div class="dept-header">
            {dept_icons.get(dept, '🏢')} {dept.upper()} DEPARTMENT
        </div>
        """
        
        for row in rows:
            row_id, user_id, title, category, department, description, image_path, timestamp, status = row

            status_colors = {
                "resolved": "#4caf50",
                "in_progress": "#ff9800",
                "pending": "#f44336"
            }
            status_color = status_colors.get(status.lower(), "#757575")
            
            # Collect image paths for gallery
            if os.path.exists(image_path):
                image_paths.append(image_path)

            html_content += f"""
            <div class="complaint-card">
                <div style="display: grid; gap: 1rem;">
                    <div>
                        <div style="color: var(--text-muted); font-size: 0.85rem; font-weight: 600;">ID: #{row_id}</div>
                        <div style="font-size: 1.3rem; font-weight: 700; color: var(--text-primary); margin: 0.25rem 0;">{title}</div>
                        <div style="color: var(--text-secondary); font-weight: 500;">Category: {category}</div>
                    </div>
                    
                    <div class="info-badge">
                        <div class="info-badge-label"> Description</div>
                        <div style="color: var(--text-secondary); line-height: 1.5; margin-top: 0.5rem;">{description}</div>
                    </div>
                    
                    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.75rem;">
                        <div class="info-badge" style="text-align: center;">
                            <div class="info-badge-label">Status</div>
                            <div style="color: {status_color}; font-weight: 700; font-size: 0.95rem; margin-top: 0.25rem;">
                                {status.replace('_', ' ').title()}
                            </div>
                        </div>
                        
                        <div class="info-badge" style="text-align: center;">
                            <div class="info-badge-label">Department</div>
                            <div class="info-badge-value" style="font-size: 0.9rem;">{department}</div>
                        </div>

                        <div class="info-badge" style="text-align: center;">
                            <div class="info-badge-label">User</div>
                            <div class="info-badge-value" style="font-size: 0.9rem;">#{user_id}</div>
                        </div>
                        
                        <div class="info-badge" style="text-align: center;">
                            <div class="info-badge-label">Time</div>
                            <div style="font-size: 0.85rem; color: var(--text-secondary); margin-top: 0.25rem;">{timestamp}</div>
                        </div>
                    </div>
                    
                    <div style="font-size: 0.85rem; color: var(--text-muted); font-style: italic;">
                         Image #{len(image_paths)} 
                    </div>
                </div>
            </div>
            """

    if html_content == '<div style="animation: fadeIn 0.6s ease;">':
        html_content += '<div style="text-align: center; padding: 3rem; color: var(--text-muted); font-size: 1.1rem;">📝 No complaints found in the system.</div>'
    
    html_content += '</div>'
    return html_content, image_paths

# ---------------- Build Gradio App ----------------
with gr.Blocks(css=custom_css, theme=gr.themes.Soft(), title="🌿 Green Civic Reporter") as demo:
    header_display = gr.HTML('<div id="header"><h1>🌿 Green Civic Reporter</h1></div>')

    current_user_state = gr.State({"uid": None, "email": None, "role": None})

    # Authentication Tab
    with gr.Tab(" Authentication"):
        with gr.Column(elem_classes=["auth-container"]):
            gr.HTML('<div class="auth-title">🌿 Welcome to Green Civic Reporter</div>')
            gr.HTML('<div style="text-align: center; color: var(--text-muted); margin-bottom: 2rem;">Sign in or create an account to report civic issues</div>')
            
            with gr.Row():
                with gr.Column(scale=1):
                    gr.HTML('<div class="section-title"> Login</div>')
                    login_email = gr.Textbox(
                        label="Email Address", 
                        placeholder="your.email@example.com"
                    )
                    login_password = gr.Textbox(
                        label="Password", 
                        type="password",
                        placeholder="Enter your password"
                    )
                    login_btn = gr.Button(" Login", elem_classes=["primary-btn"])
                
                with gr.Column(scale=1):
                    gr.HTML('<div class="section-title"> Sign Up</div>')
                    signup_email = gr.Textbox(
                        label="Email Address", 
                        placeholder="your.email@example.com"
                    )
                    signup_password = gr.Textbox(
                        label="Password", 
                        type="password",
                        placeholder="Create a password"
                    )
                    signup_btn = gr.Button(" Create Account", elem_classes=["secondary-btn"])
            
            auth_status = gr.HTML()
            signout_btn = gr.Button(" Sign Out", elem_classes=["signout-btn"])

        login_btn.click(
            login,
            inputs=[login_email, login_password, current_user_state],
            outputs=[auth_status, current_user_state, header_display]
        )
        signup_btn.click(
            signup,
            inputs=[signup_email, signup_password, current_user_state],
            outputs=[auth_status, current_user_state]
        )
        signout_btn.click(
            signout,
            inputs=[current_user_state],
            outputs=[auth_status, current_user_state, header_display]
        )

    # Citizen Dashboard
    with gr.Tab("👥 Citizen Dashboard"):
        gr.HTML('<div style="text-align: center; margin-bottom: 1.5rem; color: var(--text-secondary);">Report civic issues with AI-powered analysis</div>')
        
        with gr.Row():
            with gr.Column(scale=1):
                image_in = gr.Image(
                    type="filepath", 
                    label="📷 Upload Issue Image"
                )
                user_msg = gr.Textbox(
                    label=" Additional Notes (Optional)", 
                    placeholder="Location, severity, or any other details...",
                    lines=3
                )
                submit_btn = gr.Button(" Analyze & Submit", elem_classes=["success-btn"])
            
            with gr.Column(scale=1):
                ai_out_html = gr.HTML()
                uploaded_img_display = gr.Image(label="📷 Uploaded Issue Image", elem_classes=["image-display-card"])

        submit_btn.click(
            process_complaint,
            inputs=[image_in, user_msg, current_user_state],
            outputs=[ai_out_html, uploaded_img_display]
        )

    # Admin Dashboard
    with gr.Tab("👨‍💼 Admin Dashboard"):
        gr.HTML('<div style="text-align: center; margin-bottom: 1.5rem; color: var(--text-secondary);">Manage and review departmental complaints</div>')
        
        admin_view_btn = gr.Button("🔄 Refresh Complaints", elem_classes=["primary-btn"])
        admin_container = gr.HTML()
        
        gr.HTML('<div style="margin-top: 2rem; padding: 1rem; background: var(--bg-light); border-radius: 12px; text-align: center; font-weight: 600; color: var(--text-primary);">📸 Complaint Images Gallery</div>')
        admin_gallery = gr.Gallery(
            label="All Complaint Images",
            show_label=False,
            columns=4,
            rows=2,
            object_fit="contain",
            height="auto"
        )

        admin_view_btn.click(
            get_admin_complaints_html,
            inputs=[current_user_state],
            outputs=[admin_container]
        )

demo.launch(debug=True, favicon_path=None, share=False)