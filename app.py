import streamlit as st
import google.generativeai as genai
import json
import random
import io
from PyPDF2 import PdfReader
from streamlit_agraph import agraph, Node, Edge, Config
from datetime import datetime
import plotly.graph_objects as go
import numpy as np
import hashlib
import secrets

# --- App Configuration ---
st.set_page_config(
    page_title="Guiding North Training",
    page_icon="🧭",
    layout="wide",
)

# --- Configuration Management ---
CONFIG_FILE = "config.json"
FRAMEWORK_FILE = "guiding_north_framework.md"
KNOWLEDGE_BASE_FILE = "HRLKnowledgeBase"
WEBSITE_KB_FILE = "und_housing_website.md"
BEST_PRACTICES_FILE = "housing_best_practices.md"
RESULTS_FILE = "results.json"
USERS_FILE = "users.json"

# --- Password Security Functions ---
def hash_password(password):
    """Hash a password with a salt for secure storage."""
    salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return f"{salt}${hashed.hex()}"

def verify_password(stored_hash, password):
    """Verify a password against its stored hash."""
    try:
        salt, hash_hex = stored_hash.split('$')
        hashed = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
        return hashed.hex() == hash_hex
    except (ValueError, AttributeError):
        return False

def validate_email(email):
    """Basic email validation."""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def load_users():
    """Loads user accounts and passwords from JSON."""
    try:
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_users(users_data):
    """Saves user accounts to JSON."""
    try:
        with open(USERS_FILE, 'w') as f:
            json.dump(users_data, f, indent=4)
        return True
    except Exception as e:
        st.error(f"Error saving users: {e}")
        return False

def load_framework():
    """Loads the Guiding North Framework from the markdown file."""
    try:
        with open(FRAMEWORK_FILE, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except FileNotFoundError:
        st.error(f"Framework file not found: {FRAMEWORK_FILE}")
        return "Framework not available."

def load_knowledge_base():
    """Loads the HRL Knowledge Base file for protocols and policies."""
    try:
        with open(KNOWLEDGE_BASE_FILE, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except FileNotFoundError:
        st.error(f"Knowledge base file not found: {KNOWLEDGE_BASE_FILE}")
        return "Knowledge base not available."

def load_website_kb():
    """Loads UND Housing website notes for public info and links."""
    try:
        with open(WEBSITE_KB_FILE, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except FileNotFoundError:
        st.error(f"Website notes file not found: {WEBSITE_KB_FILE}")
        return "Website notes not available."

def load_best_practices():
    """Loads general housing best practices."""
    try:
        with open(BEST_PRACTICES_FILE, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except FileNotFoundError:
        st.error(f"Best practices file not found: {BEST_PRACTICES_FILE}")
        return "Best practices not available."

def load_results():
    """Loads the results from the JSON file."""
    try:
        with open(RESULTS_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_results(data):
    """Saves the results to the JSON file."""
    try:
        with open(RESULTS_FILE, 'w') as f:
            json.dump(data, f, indent=4)
        return True
    except Exception as e:
        st.error(f"Error saving results: {e}")
        return False

def load_config():
    """Loads the configuration from the JSON file."""
    try:
        with open(CONFIG_FILE, 'r') as f:
            config_data = json.load(f)
            # Ensure org_chart key exists
            if 'org_chart' not in config_data:
                config_data['org_chart'] = {'nodes': [], 'edges': []}
            return config_data
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "staff_roles": {},
            "org_chart": {'nodes': [], 'edges': []}
        }

def save_config(config_data):
    """Saves the configuration to config.json."""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config_data, f, indent=4)
        return True
    except Exception as e:
        st.error(f"Failed to save configuration: {e}")
        return False

# Load initial configuration
config = load_config()
STAFF_ROLES = config.get("staff_roles", {})
ORG_CHART = config.get("org_chart", {'nodes': [], 'edges': []})
GUIDING_NORTH_FRAMEWORK = load_framework()
HRL_KNOWLEDGE_BASE = load_knowledge_base()
UND_WEBSITE_KB = load_website_kb()
HOUSING_BEST_PRACTICES = load_best_practices()

def extract_text_from_pdf(pdf_file):
    """Extracts text from an uploaded PDF file."""
    try:
        pdf_reader = PdfReader(io.BytesIO(pdf_file.read()))
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text()
        return text
    except Exception as e:
        st.error(f"Error reading PDF: {e}")
        return None

# --- Gemini API Configuration ---
def configure_genai(api_key):
    """Configures the Gemini API with the provided key."""
    try:
        genai.configure(api_key=api_key)
        return True
    except Exception as e:
        st.error(f"Failed to configure Gemini API: {e}")
        return False

# --- UI: Sidebar ---
with st.sidebar:
    st.title("🧭 Guiding North")
    st.write("AI-Powered Training for the Guiding North Framework.")

    # Try to load API key from secrets (Streamlit Cloud) or allow manual input (local dev)
    api_key_secret = st.secrets.get("gemini_api_key")
    
    if api_key_secret:
        # Auto-configure using secrets (no UI input needed)
        if not st.session_state.get("api_configured"):
            if configure_genai(api_key_secret):
                st.session_state.api_configured = True
                st.success("✅ Gemini API Configured from Secrets!")
                with st.spinner("Fetching available models..."):
                    try:
                        st.session_state.models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                    except Exception as e:
                        st.error(f"Could not list models: {e}")
            else:
                st.session_state.api_configured = False
    else:
        # Manual input for local development
        api_key = st.text_input("Enter your Gemini API Key:", type="password", key="api_key_input")

        if st.button("Initialize Training Environment", key="init_button"):
            if api_key:
                if configure_genai(api_key):
                    st.session_state.api_configured = True
                    st.success("Gemini API Configured Successfully!")
                    with st.spinner("Fetching available models..."):
                        try:
                            st.session_state.models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                            # Set default model if not already set
                            if 'selected_model' not in st.session_state and st.session_state.models:
                                st.session_state.selected_model = st.session_state.models[0]
                        except Exception as e:
                            st.error(f"Could not list models: {e}")
                else:
                    st.session_state.api_configured = False
            else:
                st.warning("Please enter your Gemini API Key.")
                st.session_state.api_configured = False

# --- User Login ---
st.sidebar.header("User Login")

if 'first_name' not in st.session_state:
    st.session_state.first_name = ""
if 'last_name' not in st.session_state:
    st.session_state.last_name = ""
if 'email' not in st.session_state:
    st.session_state.email = ""
if 'position' not in st.session_state:
    st.session_state.position = ""
if 'user_role' not in st.session_state:
    st.session_state.user_role = None  # "staff" or "supervisor"
if 'direct_reports' not in st.session_state:
    st.session_state.direct_reports = []
if 'is_admin' not in st.session_state:
    st.session_state.is_admin = False

# Load existing users
users_db = load_users()

# Check if this is the first login (create admin account)
if not users_db and not st.session_state.email:
    st.sidebar.info("🔐 First time setup: Create the admin account below")
    
    with st.sidebar.expander("Create Admin Account", expanded=True):
        admin_email = st.text_input("Admin Email:", key="admin_email_setup")
        admin_password = st.text_input("Admin Password:", type="password", key="admin_password_setup")
        admin_password_confirm = st.text_input("Confirm Password:", type="password", key="admin_password_confirm_setup")
        
        if st.button("Create Admin Account", key="create_admin_btn"):
            if not admin_email or not admin_password:
                st.error("Email and password are required.")
            elif not validate_email(admin_email):
                st.error("Please enter a valid email address.")
            elif admin_email in users_db:
                st.error("This email is already registered.")
            elif admin_password != admin_password_confirm:
                st.error("Passwords do not match.")
            elif len(admin_password) < 6:
                st.error("Password must be at least 6 characters.")
            else:
                users_db[admin_email] = {
                    "password_hash": hash_password(admin_password),
                    "is_admin": True,
                    "first_name": "Admin",
                    "last_name": "Account",
                    "position": "Administrator",
                    "created_date": datetime.now().isoformat()
                }
                if save_users(users_db):
                    st.success("✅ Admin account created! You can now log in.")
                    st.rerun()

# Login form
col1, col2 = st.sidebar.columns([1, 1])
with col1:
    st.write("**Login**")

email_input = st.sidebar.text_input("Email Address:", value=st.session_state.email, key="login_email")
password_input = st.sidebar.text_input("Password:", type="password", key="login_password")

if st.sidebar.button("Login", key="login_button"):
    if not email_input or not password_input:
        st.sidebar.error("Please enter all required fields.")
    elif email_input not in users_db:
        st.sidebar.error("Email not registered. Contact your administrator.")
    elif not verify_password(users_db[email_input]["password_hash"], password_input):
        st.sidebar.error("Incorrect password.")
    else:
        # Successful login - load user data from database
        user_data = users_db[email_input]
        st.session_state.first_name = user_data.get("first_name", "User")
        st.session_state.last_name = user_data.get("last_name", "")
        st.session_state.email = email_input
        st.session_state.position = user_data.get("position", "Unknown")
        st.session_state.is_admin = user_data.get("is_admin", False)
        
        # Determine user role based on org chart
        direct_reports = []
        for edge in ORG_CHART.get('edges', []):
            if edge['target'] == st.session_state.position:
                direct_reports.append(edge['source'])
        
        st.session_state.direct_reports = direct_reports
        st.session_state.user_role = "supervisor" if direct_reports else "staff"
        
        role_label = f" (Supervisor - oversees {len(direct_reports)} role(s))" if direct_reports else " (Staff)"
        admin_label = " [ADMIN]" if st.session_state.is_admin else ""
        st.sidebar.success(f"✅ Welcome, {st.session_state.first_name}!{role_label}{admin_label}")
        st.rerun()

# Show logout and account options if logged in
if st.session_state.get("email"):
    st.sidebar.markdown("---")
    
    # Only show Account Settings expander for admin users
    if st.session_state.get("is_admin"):
        with st.sidebar.expander("🔐 Account Settings"):
            tab_change_pwd, tab_new_user, tab_manage_users = st.tabs(["Change Password", "New User (Admin)", "Manage Users (Admin)"])
            
            # Change Password Tab
            with tab_change_pwd:
                st.subheader("Change Your Password")
                current_pwd = st.text_input("Current Password:", type="password", key="current_pwd")
                new_pwd = st.text_input("New Password:", type="password", key="new_pwd")
                new_pwd_confirm = st.text_input("Confirm New Password:", type="password", key="new_pwd_confirm")
                
                if st.button("Update Password", key="update_pwd_btn"):
                    if not verify_password(users_db[st.session_state.email]["password_hash"], current_pwd):
                        st.error("Current password is incorrect.")
                    elif len(new_pwd) < 6:
                        st.error("New password must be at least 6 characters.")
                    elif new_pwd != new_pwd_confirm:
                        st.error("New passwords do not match.")
                    else:
                        users_db[st.session_state.email]["password_hash"] = hash_password(new_pwd)
                        if save_users(users_db):
                            st.success("✅ Password updated successfully!")
            
            # New User Tab (Admin Only)
            with tab_new_user:
                st.subheader("Create New User Account")
                new_email = st.text_input("User Email:", key="new_user_email")
                new_first = st.text_input("First Name:", key="new_user_first")
                new_last = st.text_input("Last Name:", key="new_user_last")
                new_position = st.selectbox("Position/Role:", list(STAFF_ROLES.keys()), key="new_user_position")
                new_pwd_admin = st.text_input("Temporary Password:", type="password", key="new_user_pwd")
                new_is_admin = st.checkbox("Grant admin privileges", key="new_user_admin")
                
                if st.button("Create User", key="create_user_btn"):
                    if not new_email or not new_first or not new_pwd_admin:
                        st.error("Email, name, and password are required.")
                    elif not validate_email(new_email):
                        st.error("Please enter a valid email address.")
                    elif new_email.lower() in [k.lower() for k in users_db.keys()]:
                        st.error("This email is already registered (case-insensitive check).")
                    elif len(new_pwd_admin) < 6:
                        st.error("Password must be at least 6 characters.")
                    else:
                        users_db[new_email] = {
                            "password_hash": hash_password(new_pwd_admin),
                            "is_admin": new_is_admin,
                            "first_name": new_first,
                            "last_name": new_last,
                            "position": new_position,
                            "created_date": datetime.now().isoformat()
                        }
                        if save_users(users_db):
                            st.success(f"✅ User {new_email} created with temporary password!")
            
            # Manage Users Tab (Admin Only)
            with tab_manage_users:
                st.subheader("Manage User Accounts")
                
                if users_db:
                    user_to_manage = st.selectbox("Select User:", list(users_db.keys()), key="manage_user_select")
                    
                    if user_to_manage:
                        user_info = users_db[user_to_manage]
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.write(f"**Name:** {user_info.get('first_name')} {user_info.get('last_name')}")
                            st.write(f"**Position:** {user_info.get('position')}")
                            st.write(f"**Admin:** {'Yes' if user_info.get('is_admin') else 'No'}")
                        
                        with col2:
                            if st.button("Reset Password", key="reset_pwd_btn"):
                                temp_pwd = secrets.token_urlsafe(8)
                                users_db[user_to_manage]["password_hash"] = hash_password(temp_pwd)
                                if save_users(users_db):
                                    st.success(f"✅ Password reset! Temporary password: `{temp_pwd}`")
                            
                            if user_to_manage != st.session_state.email:
                                if st.button("Delete User", key="delete_user_btn"):
                                    del users_db[user_to_manage]
                                    if save_users(users_db):
                                        st.success(f"✅ User {user_to_manage} deleted.")
                                        st.rerun()
                else:
                    st.info("No users to manage.")
    
    if st.sidebar.button("Logout", key="logout_btn"):
        for key in list(st.session_state.keys()):
            if key not in ['api_configured', 'selected_model', 'api_key']:
                del st.session_state[key]
        st.rerun()

# Main content is only displayed if the user has logged in and the API is configured
if st.session_state.get("email") and st.session_state.get("api_configured"):
    # Initialize model with default if not set
    if 'selected_model' not in st.session_state:
        if st.session_state.get('models'):
            st.session_state.selected_model = st.session_state.models[0]
        else:
            st.session_state.selected_model = 'gemini-2.0-flash-exp'  # Fallback default
    
    model = genai.GenerativeModel(st.session_state.selected_model)

    # Build tab list based on user role
    if st.session_state.get("is_admin"):
        tab_names = [
            "Scenario Simulator",
            "Tone Polisher",
            "Call Analysis",
            "Org Chart",
            "Configuration",
            "Results & Progress"
        ]
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(tab_names)
        org_chart_tab = tab4
        results_tab = tab6
    else:
        tab_names = [
            "Scenario Simulator",
            "Tone Polisher",
            "Org Chart",
            "Results & Progress"
        ]
        tab1, tab2, tab3, tab4 = st.tabs(tab_names)
        org_chart_tab = tab3
        results_tab = tab4

    with tab1:
        st.header("Scenario Simulator")
        st.write("Practice applying the Guiding North Framework in realistic situations.")

        if not STAFF_ROLES:
             st.warning("No staff roles configured. Please add roles in the Configuration tab.")
             st.stop()

        # Staff can only practice their own role, supervisors can practice any of their direct reports' roles
        available_roles = [st.session_state.position] if st.session_state.position else list(STAFF_ROLES.keys())
        
        selected_role = st.selectbox("Select Your Role:", available_roles, key="role_selector")
        difficulty = st.selectbox(
            "Scenario Difficulty:",
            ["Easier than average", "Average", "Harder than average"],
            key="difficulty_selector"
        )

        if "scenario" not in st.session_state:
            st.session_state.scenario = ""
        if "evaluation" not in st.session_state:
            st.session_state.evaluation = ""

        if st.button("🎲 Generate New Scenario", key="generate_scenario_button"):
            with st.spinner("Generating a new scenario..."):
                role_info = STAFF_ROLES[selected_role]
                last_scenario_text = st.session_state.scenario.strip() if st.session_state.scenario else "None"
                prompt = f"""
                **System Grounding:** You are an expert training assistant for the University of North Dakota Housing & Residence Life, specializing in the Guiding NORTH Framework. Your primary tool is the following document:

                ---
                {GUIDING_NORTH_FRAMEWORK}
                ---

                **Operational Knowledge Base (protocols & policies):**
                ---
                {HRL_KNOWLEDGE_BASE}
                ---

                **UND Housing Website Notes (public info & links):**
                ---
                {UND_WEBSITE_KB}
                ---

                **Best Practices (on‑campus housing):**
                ---
                {HOUSING_BEST_PRACTICES}
                ---

                **Organizational Structure:**
                ---
                The '{selected_role}' reports to: {role_info.get('supervisor', 'Not specified')}
                
                Organizational Chart Reporting Relationships:
                {chr(10).join([f"- {edge['source']} reports to {edge['target']}" for edge in ORG_CHART.get('edges', [])])}
                ---

                **Role Description/Job Details:**
                ---
                {role_info.get('description', 'Not provided.')}
                ---

                **Task:** Based *only* on the framework document provided, generate a single, detailed, and realistic customer service scenario for a '{selected_role}'.
                - **Difficulty:** {difficulty}.
                - **Variety requirement:** Do NOT repeat the same type of scenario as the previous one. If the previous scenario involved a lockout, do not use a lockout scenario this time.
                - **Scenario variety examples (pick a different one each time):** roommate conflict, noise complaint, policy clarification, guest policy issue, maintenance/repairs, conduct concern, alcohol/drug concern, safety/wellness check, mental health support, accessibility or accommodation request, bias/incident response, community conflict, emergency response, damaged property, billing question.

                **Previous Scenario (for variety check only):**
                {last_scenario_text}

                The scenario should be a full paragraph and must be something this person would likely encounter in their role at UND Housing. It must be designed to test their proficiency in one or more pillars of the Guiding NORTH framework.
                """
                try:
                    response = model.generate_content(
                        prompt,
                        generation_config=genai.types.GenerationConfig(
                            temperature=0.9,
                            max_output_tokens=15000
                        )
                    )
                    st.session_state.scenario = response.text
                    st.session_state.evaluation = "" # Clear previous evaluation
                except Exception as e:
                    st.error(f"Error generating scenario: {e}")

        if st.session_state.scenario:
            st.info(f"**Your Scenario:**\n\n{st.session_state.scenario}")
            
            user_response = st.text_area("Your Response:", height=150, key="response_input")

            if st.button("✨ Evaluate My Response", key="evaluate_response_button"):
                if user_response:
                    with st.spinner("The AI is evaluating your response..."):
                        role_info = STAFF_ROLES[selected_role]
                        eval_prompt = f"""
                        **System Grounding:** You are an expert training assistant for the University of North Dakota Housing & Residence Life, specializing in the Guiding NORTH Framework. Your analysis MUST be based *strictly* on the following framework document:

                        ---
                        {GUIDING_NORTH_FRAMEWORK}
                        ---

                        **Operational Knowledge Base (protocols & policies):**
                        ---
                        {HRL_KNOWLEDGE_BASE}
                        ---

                        **UND Housing Website Notes (public info & links):**
                        ---
                        {UND_WEBSITE_KB}
                        ---

                        **Best Practices (on‑campus housing):**
                        ---
                        {HOUSING_BEST_PRACTICES}
                        ---

                        **Organizational Structure:**
                        ---
                        The '{selected_role}' reports to: {role_info.get('supervisor', 'Not specified')}
                        
                        Organizational Chart Reporting Relationships:
                        {chr(10).join([f"- {edge['source']} reports to {edge['target']}" for edge in ORG_CHART.get('edges', [])])}
                        ---

                        **Context for Evaluation:**
                        - **Role:** {selected_role}
                        - **Job Description/Role Details:** {role_info.get('description', 'Not provided.')}
                        - **Scenario:** {st.session_state.scenario}
                        - **User's Response:** {user_response}

                        **Task:** Evaluate the user's response using the 'Evaluation Rubric' from the framework document. 
                        1. Provide an 'Overall Score' from 1 (Needs Improvement) to 5 (Exemplary).
                        2. For each of the five pillars (N, O, R, T, H), assign a rating (Needs Development, Proficient, or Exemplary) and provide a brief justification for your rating, citing specific examples from the user's response. 
                        3. Conclude with a full, detailed 'Exemplary Response Example' that demonstrates how a top-performing staff member would have handled the interaction from start to finish.

                        **Output Format (Strict):**
                        ### Guiding NORTH Evaluation:

                        **Overall Score:** [Your 1-5 Rating]

                        ---

                        **N - Navigate Needs:**
                        - **Rating:** [Your Rating]
                        - **Justification:** [Your Justification]

                        **O - Own the Outcome:**
                        - **Rating:** [Your Rating]
                        - **Justification:** [Your Justification]

                        **R - Respond Respectfully:**
                        - **Rating:** [Your Rating]
                        - **Justification:** [Your Justification]

                        **T - Timely & Truthful:**
                        - **Rating:** [Your Rating]
                        - **Justification:** [Your Justification]

                        **H - Help Proactively:**
                        - **Rating:** [Your Rating]
                        - **Justification:** [Your Justification]

                        ---
                        **Exemplary Response Example:**
                        [Provide a full, detailed, and exemplary response to the original scenario here.]
                        """
                        try:
                            evaluation_response = model.generate_content(
                                eval_prompt,
                                generation_config=genai.types.GenerationConfig(
                                    temperature=0.5,
                                    max_output_tokens=15000
                                )
                            )
                            st.session_state.evaluation = evaluation_response.text
                            st.rerun() # Rerun to show the save button
                        except Exception as e:
                            st.error(f"An error occurred during evaluation: {e}")
                else:
                    st.warning("Please enter your response before evaluating.")
            
            if st.session_state.evaluation:
                st.markdown("### Evaluation:")
                st.markdown(st.session_state.evaluation)

                if st.button("💾 Save Result", key="save_result"):
                    results = load_results()
                    # Extract overall score from the evaluation text
                    overall_score = "Not Found"
                    for line in st.session_state.evaluation.splitlines():
                        if "Overall Score:" in line:
                            try:
                                overall_score = line.split(":")[1].strip()
                            except IndexError:
                                overall_score = "Parse Error"
                            break
                    
                    new_result = {
                        "first_name": st.session_state.first_name,
                        "last_name": st.session_state.last_name,
                        "email": st.session_state.email,
                        "timestamp": datetime.now().isoformat(),
                        "role": selected_role,
                        "difficulty": difficulty,
                        "scenario": st.session_state.scenario,
                        "user_response": user_response,
                        "evaluation": st.session_state.evaluation,
                        "overall_score": overall_score
                    }
                    results.append(new_result)
                    if save_results(results):
                        st.success("Result saved successfully!")
                    else:
                        st.error("Failed to save the result.")

    with tab2:
        st.header("AI-Powered Tone Polisher")
        st.write("Refine your professional communication to be more strengths-based and aligned with the Guiding North Framework.")
        
        text_to_polish = st.text_area("Enter text to polish (e.g., an email, a case note, a text to a youth):", height=200, key="polish_input")

        if st.button("Polish My Text", key="polish_button"):
            if text_to_polish:
                with st.spinner("Polishing your text..."):
                    polish_prompt = f"""
                    **Task:** Rewrite the following text to be more relational, strengths-based, and trauma-informed, ensuring it is consistent with the Guiding North Framework. The original meaning should be preserved, but the tone must be improved.

                    **Original Text:**
                    "{text_to_polish}"

                    **Polished Text:**
                    """
                    try:
                        # This assumes 'model' is defined and configured earlier, e.g., in the sidebar
                        if 'selected_model' in st.session_state and st.session_state.api_configured:
                            model = genai.GenerativeModel(st.session_state.selected_model)
                            polished_response = model.generate_content(
                                polish_prompt,
                                generation_config=genai.types.GenerationConfig(
                                    temperature=0.6,
                                    max_output_tokens=500
                                )
                            )
                            st.markdown("**Suggested Revision:**")
                            st.markdown(polished_response.text)
                        else:
                            st.error("API is not configured. Please initialize it in the sidebar.")
                    except Exception as e:
                        st.error(f"Error polishing text: {e}")
            else:
                st.warning("Please enter some text to polish.")

    # Call Analysis Tab - Admin Only
    if st.session_state.get("is_admin"):
        with tab3:
            st.header("Call Analysis")
            st.write("Analyze customer phone call transcripts based on the Guiding North Framework.")
            
            # User Information
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                call_first_name = st.text_input("First Name:", key="call_first_name")
            with col2:
                call_last_name = st.text_input("Last Name:", key="call_last_name")
            with col3:
                call_email = st.text_input("Email:", key="call_email")
            with col4:
                call_role = st.selectbox("Role:", list(STAFF_ROLES.keys()), key="call_role")
            
            analysis_method = st.radio(
                "Input Method:",
                ["Paste Transcript", "Upload Audio"],
                key="analysis_method"
            )
            
            if analysis_method == "Paste Transcript":
                call_transcript = st.text_area(
                    "Paste the call transcript below:",
                    height=300,
                    placeholder="Example:\nAgent: Hello, this is Housing. How can I help you today?\nCaller: Hi, I'm locked out of my room...\n\n(Include the full conversation)",
                    key="call_transcript"
                )
                
                if st.button("🔍 Analyze Call", key="analyze_call_button"):
                    if call_transcript and call_first_name and call_last_name:
                        with st.spinner("Analyzing the call transcript..."):
                            role_info = STAFF_ROLES[call_role]
                            analysis_prompt = f"""
                            **System Grounding:** You are an expert training assistant for the University of North Dakota Housing & Residence Life, specializing in the Guiding NORTH Framework. Your analysis MUST be based *strictly* on the following framework document:

                            ---
                            {GUIDING_NORTH_FRAMEWORK}
                            ---

                            **Operational Knowledge Base (protocols & policies):**
                            ---
                            {HRL_KNOWLEDGE_BASE}
                            ---

                            **UND Housing Website Notes (public info & links):**
                            ---
                            {UND_WEBSITE_KB}
                            ---

                            **Best Practices (on‑campus housing):**
                            ---
                            {HOUSING_BEST_PRACTICES}
                            ---

                            **Organizational Structure:**
                            ---
                            The '{call_role}' reports to: {role_info.get('supervisor', 'Not specified')}
                            
                            Organizational Chart Reporting Relationships:
                            {chr(10).join([f"- {edge['source']} reports to {edge['target']}" for edge in ORG_CHART.get('edges', [])])}
                            ---

                            **Role Description/Job Details:**
                            ---
                            {role_info.get('description', 'Not provided.')}
                            ---

                            **Context for Evaluation:**
                            - **Role:** {call_role}
                            - **Staff Member:** {call_first_name} {call_last_name}
                            - **Call Transcript:** {call_transcript}

                            **Task:** Evaluate the staff member's phone call performance using the 'Evaluation Rubric' from the framework document.
                            1. Provide an 'Overall Score' from 1 (Needs Improvement) to 5 (Exemplary).
                            2. For each of the five pillars (N, O, R, T, H), assign a rating (Needs Development, Proficient, or Exemplary) and provide a brief justification for your rating, citing specific examples from the call transcript.
                            3. Provide specific suggestions for improvement where applicable.
                            4. Conclude with a full, detailed 'Exemplary Call Example' that demonstrates how a top-performing staff member would have handled the call from start to finish.

                            **Output Format (Strict):**
                            ### Guiding NORTH Evaluation:

                            **Overall Score:** [Your 1-5 Rating]

                            ---

                            **N - Navigate Needs:**
                            - **Rating:** [Your Rating]
                            - **Justification:** [Your Justification]

                            **O - Own the Outcome:**
                            - **Rating:** [Your Rating]
                            - **Justification:** [Your Justification]

                            **R - Respect & Relationships:**
                            - **Rating:** [Your Rating]
                            - **Justification:** [Your Justification]

                            **T - Trust Through Transparency:**
                            - **Rating:** [Your Rating]
                            - **Justification:** [Your Justification]

                            **H - Hope & Healing:**
                            - **Rating:** [Your Rating]
                            - **Justification:** [Your Justification]

                            ---

                            ### Suggestions for Improvement:
                            [Your Suggestions]

                            ---

                            ### Exemplary Call Example:
                            [Your Detailed Example]
                            """
                            try:
                                if 'selected_model' in st.session_state and st.session_state.api_configured:
                                    model = genai.GenerativeModel(st.session_state.selected_model)
                                    analysis_response = model.generate_content(
                                        analysis_prompt,
                                        generation_config=genai.types.GenerationConfig(
                                            temperature=0.7,
                                            max_output_tokens=15000
                                        )
                                    )
                                    st.markdown("### 📊 Call Analysis Results")
                                    st.markdown(analysis_response.text)
                                    
                                    # Extract overall score
                                    overall_score = "Not Found"
                                    for line in analysis_response.text.splitlines():
                                        if "Overall Score:" in line:
                                            try:
                                                overall_score = line.split(":")[1].strip()
                                            except IndexError:
                                                overall_score = "Parse Error"
                                            break
                                    
                                    # Save result
                                    results = load_results()
                                    new_result = {
                                        "first_name": call_first_name,
                                        "last_name": call_last_name,
                                        "email": call_email,
                                        "timestamp": datetime.now().isoformat(),
                                        "role": call_role,
                                        "difficulty": "Call Analysis",
                                        "scenario": f"Phone Call Transcript (Length: {len(call_transcript)} chars)",
                                        "user_response": call_transcript,
                                        "evaluation": analysis_response.text,
                                        "overall_score": overall_score
                                    }
                                    results.append(new_result)
                                    if save_results(results):
                                        st.success("Call analysis saved successfully!")
                                    else:
                                        st.error("Failed to save the analysis.")
                                else:
                                    st.error("API is not configured. Please initialize it in the sidebar.")
                            except Exception as e:
                                st.error(f"Error analyzing call: {e}")
                    else:
                        st.warning("Please provide your name and paste a call transcript to analyze.")
            else:
                # Audio upload option using Gemini
                st.write("Upload an audio recording of the call:")
                st.info("📝 Gemini will transcribe and analyze the audio in one step.")
                
                uploaded_audio = st.file_uploader(
                    "Choose an audio file",
                    type=['mp3', 'mp4', 'mpeg', 'mpga', 'm4a', 'wav', 'webm', 'flac'],
                    key="audio_upload"
                )
                
                if uploaded_audio:
                    st.audio(uploaded_audio, format=uploaded_audio.type)
                    
                    if st.button("🎤 Transcribe & Analyze Call", key="transcribe_analyze_button"):
                        if call_first_name and call_last_name:
                            with st.spinner("Processing audio and analyzing call..."):
                                try:
                                    # Upload audio file to Gemini
                                    audio_file = genai.upload_file(uploaded_audio, mime_type=uploaded_audio.type)
                                    
                                    role_info = STAFF_ROLES[call_role]
                                    analysis_prompt = f"""
                                    **System Grounding:** You are an expert training assistant for the University of North Dakota Housing & Residence Life, specializing in the Guiding NORTH Framework. Your analysis MUST be based *strictly* on the following framework document:

                                    ---
                                    {GUIDING_NORTH_FRAMEWORK}
                                    ---

                                    **Operational Knowledge Base (protocols & policies):**
                                    ---
                                    {HRL_KNOWLEDGE_BASE}
                                    ---

                                    **UND Housing Website Notes (public info & links):**
                                    ---
                                    {UND_WEBSITE_KB}
                                    ---

                                    **Best Practices (on‑campus housing):**
                                    ---
                                    {HOUSING_BEST_PRACTICES}
                                    ---

                                    **Organizational Structure:**
                                    ---
                                    The '{call_role}' reports to: {role_info.get('supervisor', 'Not specified')}
                                    
                                    Organizational Chart Reporting Relationships:
                                    {chr(10).join([f"- {edge['source']} reports to {edge['target']}" for edge in ORG_CHART.get('edges', [])])}
                                    ---

                                    **Role Description/Job Details:**
                                    ---
                                    {role_info.get('description', 'Not provided.')}
                                    ---

                                    **Context for Evaluation:**
                                    - **Role:** {call_role}
                                    - **Staff Member:** {call_first_name} {call_last_name}
                                    - **Audio:** Please transcribe and analyze the audio recording provided.

                                    **Task:** 
                                    1. First, provide a complete transcript of the phone call.
                                    2. Then, evaluate the staff member's phone call performance using the 'Evaluation Rubric' from the framework document.
                                    3. Provide an 'Overall Score' from 1 (Needs Improvement) to 5 (Exemplary).
                                    4. For each of the five pillars (N, O, R, T, H), assign a rating (Needs Development, Proficient, or Exemplary) and provide a brief justification for your rating, citing specific examples from the call.
                                    5. Provide specific suggestions for improvement where applicable.
                                    6. Conclude with a full, detailed 'Exemplary Call Example' that demonstrates how a top-performing staff member would have handled the call from start to finish.

                                    **Output Format (Strict):**
                                    ### Call Transcript:
                                    [Full transcript of the call]

                                    ---

                                    ### Guiding NORTH Evaluation:

                                    **Overall Score:** [Your 1-5 Rating]

                                    ---

                                    **N - Navigate Needs:**
                                    - **Rating:** [Your Rating]
                                    - **Justification:** [Your Justification]

                                    **O - Own the Outcome:**
                                    - **Rating:** [Your Rating]
                                    - **Justification:** [Your Justification]

                                    **R - Respect & Relationships:**
                                    - **Rating:** [Your Rating]
                                    - **Justification:** [Your Justification]

                                    **T - Trust Through Transparency:**
                                    - **Rating:** [Your Rating]
                                    - **Justification:** [Your Justification]

                                    **H - Hope & Healing:**
                                    - **Rating:** [Your Rating]
                                    - **Justification:** [Your Justification]

                                    ---

                                    ### Suggestions for Improvement:
                                    [Your Suggestions]

                                    ---

                                    ### Exemplary Call Example:
                                    [Your Detailed Example]
                                    """
                                    
                                    if st.session_state.api_configured:
                                        model = genai.GenerativeModel(st.session_state.selected_model)
                                        analysis_response = model.generate_content(
                                            [audio_file, analysis_prompt],
                                            generation_config=genai.types.GenerationConfig(
                                                temperature=0.7,
                                                max_output_tokens=15000
                                            )
                                        )
                                        
                                        st.markdown("### 📊 Call Analysis Results")
                                        st.markdown(analysis_response.text)
                                        
                                        # Extract overall score
                                        overall_score = "Not Found"
                                        for line in analysis_response.text.splitlines():
                                            if "Overall Score:" in line:
                                                try:
                                                    overall_score = line.split(":")[1].strip()
                                                except IndexError:
                                                    overall_score = "Parse Error"
                                                break
                                        
                                        # Save result
                                        results = load_results()
                                        new_result = {
                                            "first_name": call_first_name,
                                            "last_name": call_last_name,
                                            "email": call_email,
                                            "timestamp": datetime.now().isoformat(),
                                            "role": call_role,
                                            "difficulty": "Call Analysis (Audio)",
                                            "scenario": f"Phone Call Recording ({uploaded_audio.name})",
                                            "user_response": analysis_response.text[:1000],  # Store first 1000 chars of full response
                                            "evaluation": analysis_response.text,
                                            "overall_score": overall_score
                                        }
                                        results.append(new_result)
                                        if save_results(results):
                                            st.success("Call analysis saved successfully!")
                                        else:
                                            st.error("Failed to save the analysis.")
                                    else:
                                        st.error("Gemini API is not configured. Please initialize it in the sidebar.")
                                    
                                except Exception as e:
                                    st.error(f"Error during audio analysis: {e}")
                        else:
                            st.warning("Please provide your name before analyzing the call.")

    with org_chart_tab:
        st.header("Organizational Chart")
        st.write("Visualizing the reporting structure of your department.")

        # Update nodes from staff roles
        ORG_CHART['nodes'] = list(STAFF_ROLES.keys())
        config['org_chart'] = ORG_CHART
        save_config(config)

        if not ORG_CHART['nodes']:
            st.warning("No staff roles defined. Please add roles in the Configuration tab to build the chart.")
        else:
            nodes = [Node(id=role, label=role, size=25) for role in ORG_CHART['nodes']]
            edges = [Edge(source=edge['source'], target=edge['target'], label="reports to") for edge in ORG_CHART.get('edges', [])]
            
            agraph_config = Config(width=750, 
                                 height=500, 
                                 directed=True, 
                                 physics=True, 
                                 hierarchical=False,
                                 # **kwargs
                                 )

            agraph(nodes=nodes, edges=edges, config=agraph_config)


    # Configuration Tab - Admin Only
    if st.session_state.get("is_admin"):
        with tab5:
            st.header("Application Configuration")
            st.write("Manage staff roles, job descriptions, and organizational structure.")

            # Gemini Model Selector
            st.subheader("AI Model Configuration")
            if st.session_state.get("api_configured"):
                if st.session_state.get("models"):
                    st.session_state.selected_model = st.selectbox(
                        "Select Gemini Model:",
                        st.session_state.get("models", []),
                        help="Choose which Gemini model to use for scenario generation and evaluation"
                    )
                    st.info(f"Currently using: **{st.session_state.selected_model}**")
                else:
                    st.warning("Could not retrieve a list of models. Please check API key permissions.")
            else:
                st.warning("Please configure the Gemini API key first.")

            st.divider()

            # Org Chart Management
            st.subheader("Define Organizational Structure")
            with st.expander("Add Roles & Define Structure", expanded=True):
                st.markdown("##### Add New Role to Chart")
                new_role_name = st.text_input("New Role Name:", key="new_role_name_org")
                if st.button("Add Role", key="add_role_org_button"):
                    if new_role_name and new_role_name not in STAFF_ROLES:
                        STAFF_ROLES[new_role_name] = {
                            "description": "Please upload a PDF job description below.",
                            "system_instruction": f"You are a practice partner for a {new_role_name}. Evaluate responses based on their job description and the Guiding North Framework."
                        }
                        config["staff_roles"] = STAFF_ROLES
                        if save_config(config):
                            st.success(f"Role '{new_role_name}' added to chart and roles list!")
                            st.rerun()
                    else:
                        st.error("Role name cannot be empty or already exist.")

                if not STAFF_ROLES or len(STAFF_ROLES) < 2:
                    st.info("You need at least two roles to define a reporting structure.")
                else:
                    role_names = list(STAFF_ROLES.keys())
                    col1, col2, col3 = st.columns([3, 3, 1])
                    with col1:
                        subordinate = st.selectbox("Subordinate Role:", options=role_names, key="subordinate_select")
                    with col2:
                        manager = st.selectbox("Manager Role:", options=role_names, key="manager_select")
                    with col3:
                        st.write("") # Spacer
                        st.write("") # Spacer
                        if st.button("Add Relationship", key="add_relationship"):
                            if subordinate and manager and subordinate != manager:
                                new_edge = {"source": subordinate, "target": manager}
                                if new_edge not in ORG_CHART.get('edges', []):
                                    ORG_CHART.setdefault('edges', []).append(new_edge)
                                    config['org_chart'] = ORG_CHART
                                    if save_config(config):
                                        st.success(f"Added: {subordinate} reports to {manager}")
                                        st.rerun()
                                else:
                                    st.warning("This relationship already exists.")
                            else:
                                st.error("Please select two different roles.")
                
                st.markdown("##### Current Reporting Structure")
                if not ORG_CHART.get('edges'):
                    st.info("No reporting relationships defined yet.")
                else:
                    for i, edge in enumerate(list(ORG_CHART['edges'])):
                        st.markdown(f"- **{edge['source']}** reports to **{edge['target']}**")
                        if st.button(f"Remove", key=f"remove_edge_{i}"):
                            ORG_CHART['edges'].pop(i)
                            config['org_chart'] = ORG_CHART
                            if save_config(config):
                                st.success("Relationship removed.")
                                st.rerun()

            # Role Detail Management
            st.subheader("Manage Role Details")
            with st.expander("Upload Job Descriptions and Delete Roles", expanded=False):
                if not STAFF_ROLES:
                    st.info("No roles configured yet.")
                else:
                    for role_name, role_data in list(STAFF_ROLES.items()):
                        st.markdown(f"**Edit Role: {role_name}**")
                        st.text_area(
                            "Role Description (from PDF):", 
                            value=role_data.get('description', ''), 
                            height=150, 
                            key=f"desc_{role_name}",
                            disabled=True
                        )
                        
                        uploaded_file = st.file_uploader(
                            "Upload new PDF Job Description", 
                            type="pdf", 
                            key=f"pdf_{role_name}"
                        )

                        if uploaded_file is not None:
                            pdf_text = extract_text_from_pdf(uploaded_file)
                            if pdf_text:
                                STAFF_ROLES[role_name]['description'] = pdf_text
                                config["staff_roles"] = STAFF_ROLES
                                if save_config(config):
                                    st.success(f"Job description for '{role_name}' updated from PDF.")
                                    st.rerun()

                        if st.button(f"Delete Role: {role_name}", key=f"delete_{role_name}"):
                            del STAFF_ROLES[role_name]
                            # Also remove from org chart edges
                            ORG_CHART['edges'] = [e for e in ORG_CHART.get('edges', []) if e['source'] != role_name and e['target'] != role_name]
                            config["staff_roles"] = STAFF_ROLES
                            config["org_chart"] = ORG_CHART
                            if save_config(config):
                                st.success(f"Role '{role_name}' deleted.")
                            st.rerun()
                    st.divider()

    with results_tab:
        st.header("Results & Progress")
        st.write("Review past performance and track development.")

        results_data = load_results()

        if not results_data:
            st.info("No results have been saved yet.")
        else:
            # Filter results based on user role and access permissions
            if st.session_state.get('is_admin'):
                # Admin sees: ALL scores
                filtered_results = results_data
                st.info(f"📊 Admin view: Viewing all results from all users ({len(results_data)} total).")
            elif st.session_state.get('user_role') == 'supervisor':
                # Supervisor sees: their own scores + all direct reports' scores
                allowed_emails = [st.session_state.email] + [
                    res.get('email') for res in results_data 
                    if res.get('role') in st.session_state.direct_reports
                ]
                filtered_results = [res for res in results_data if res.get('email') in allowed_emails]
                st.info(f"📊 You are viewing your results and your {len(st.session_state.direct_reports)} direct report role(s).")
            else:
                # Staff sees: only their own scores
                filtered_results = [res for res in results_data if res.get('email') == st.session_state.email]
                st.info(f"📊 You are viewing your own results only.")
            
            if not filtered_results:
                st.warning("No results found for your access level.")
            else:
                # Get unique roles from filtered results
                all_roles = sorted(list(set(res.get("role", "Unknown") for res in filtered_results if res.get("role"))))
                
                # Create tabs for each role
                role_tabs = st.tabs(["All Roles"] + all_roles)
                
                # Function to display role analytics
                def display_role_analytics(role_results, role_name="All Users"):
                    if not role_results:
                        st.info(f"No results found for {role_name}.")
                        return
                    
                    # Extract all scores for this role group
                    all_role_scores = []
                    for res in role_results:
                        score_str = str(res.get("overall_score", "0")).strip()
                        if score_str.isdigit():
                            all_role_scores.append(int(score_str))
                        else:
                            first_digit = next((char for char in score_str if char.isdigit()), None)
                            if first_digit:
                                all_role_scores.append(int(first_digit))
                    
                    # Calculate role group average
                    role_group_avg = (sum(all_role_scores) / len(all_role_scores)) if all_role_scores else 0
                    
                    # Filter by individual user (using email as unique identifier)
                    all_users_in_role = []
                    for res in role_results:
                        if "email" in res:
                            full_name = f"{res.get('first_name', '')} {res.get('last_name', '')} ({res['email']})"
                            all_users_in_role.append((res['email'], full_name))
                        elif "user_name" in res:
                            all_users_in_role.append((res['user_name'], res['user_name']))
                    
                    all_users_in_role = sorted(list(set(all_users_in_role)), key=lambda x: x[1])
                    user_display_names = ["All Users in Role"] + [name for _, name in all_users_in_role]
                    user_emails = ["All Users in Role"] + [email for email, _ in all_users_in_role]
                    
                    selected_display = st.selectbox(f"Filter by User ({role_name}):", options=user_display_names, key=f"user_select_{role_name}")
                    selected_user_id = user_emails[user_display_names.index(selected_display)]

                    if selected_user_id == "All Users in Role":
                        filtered_role_results = role_results
                        is_group_view = True
                    else:
                        filtered_role_results = [res for res in role_results 
                                           if res.get("email") == selected_user_id or res.get("user_name") == selected_user_id]
                        is_group_view = False

                    st.subheader(f"Displaying Results for: {selected_display}")

                    # Display summary statistics
                    if filtered_role_results:
                        scores = []
                        for res in filtered_role_results:
                            score_str = str(res.get("overall_score", "0")).strip()
                            if score_str.isdigit():
                                scores.append(int(score_str))
                            else:
                                first_digit = next((char for char in score_str if char.isdigit()), None)
                                if first_digit:
                                    scores.append(int(first_digit))
                        
                        # Display metrics with role comparison
                        col1, col2, col3, col4 = st.columns(4)
                        
                        with col1:
                            if scores:
                                avg_score = sum(scores) / len(scores)
                                st.metric(label="Your Average Score", value=f"{avg_score:.2f} / 5")
                            else:
                                st.metric(label="Your Average Score", value="N/A")
                        
                        with col2:
                            if not is_group_view:
                                # Show comparison to role group (individual avg - group avg)
                                user_avg = sum(scores) / len(scores) if scores else 0
                                comparison = user_avg - role_group_avg
                                st.metric(label="vs Role Group Average", value=f"{role_group_avg:.2f} / 5",
                                        delta=f"{comparison:+.2f}" if comparison != 0 else "Same",
                                        delta_color="normal")
                            else:
                                st.metric(label=f"{role_name} Group Average", value=f"{role_group_avg:.2f} / 5")
                        
                        with col3:
                            st.metric(label="Total Scenarios Completed", value=len(filtered_role_results))
                        
                        with col4:
                            if len(scores) >= 2:
                                midpoint = len(scores) // 2
                                first_half_avg = sum(scores[:midpoint]) / midpoint if midpoint > 0 else 0
                                second_half_avg = sum(scores[midpoint:]) / (len(scores) - midpoint)
                                improvement = second_half_avg - first_half_avg
                                st.metric(label="Improvement Trend", value=f"{improvement:+.2f}", 
                                         delta=f"{improvement:+.2f} points",
                                         delta_color="normal" if improvement >= 0 else "inverse")
                            else:
                                st.metric(label="Improvement Trend", value="N/A")

                        # Display score progression chart with trendline
                        st.markdown("---")
                        st.subheader("Score Progression Over Time")
                        
                        # Prepare data for chart
                        chart_data = []
                        for idx, res in enumerate(filtered_role_results):
                            score_str = str(res.get("overall_score", "0")).strip()
                            score = None
                            if score_str.isdigit():
                                score = int(score_str)
                            else:
                                first_digit = next((char for char in score_str if char.isdigit()), None)
                                if first_digit:
                                    score = int(first_digit)
                            
                            if score:
                                chart_data.append({
                                    "attempt": idx + 1,
                                    "score": score,
                                    "date": res.get("timestamp", "N/A")[:10],
                                    "difficulty": res.get("difficulty", "N/A")
                                })
                        
                        if chart_data:
                            # Create plotly figure with trendline
                            fig = go.Figure()
                            
                            attempts = [d["attempt"] for d in chart_data]
                            scores_plot = [d["score"] for d in chart_data]
                            dates = [d["date"] for d in chart_data]
                            
                            # Add scatter plot
                            fig.add_trace(go.Scatter(
                                x=attempts,
                                y=scores_plot,
                                mode='lines+markers',
                                name='Score',
                                line=dict(color='#1f77b4', width=2),
                                marker=dict(size=8)
                            ))
                            
                            # Add trendline
                            z = np.polyfit(attempts, scores_plot, 1)
                            p = np.poly1d(z)
                            trendline = p(np.array(attempts))
                            
                            fig.add_trace(go.Scatter(
                                x=attempts,
                                y=trendline,
                                mode='lines',
                                name='Trend',
                                line=dict(color='red', width=2, dash='dash')
                            ))
                            
                            fig.update_layout(
                                title="Score Progression with Trendline",
                                xaxis_title="Attempt Number",
                                yaxis_title="Score (out of 5)",
                                hovermode='x unified',
                                height=400,
                                yaxis=dict(range=[0, 5])
                            )
                            
                            st.plotly_chart(fig, use_container_width=True, key=f"score_progression_{role_name}")

                        # Categorize scores by difficulty
                        st.markdown("---")
                        st.subheader("Performance by Difficulty Level")
                        
                        difficulty_scores = {}
                        for res in filtered_role_results:
                            difficulty = res.get("difficulty", "N/A")
                            score_str = str(res.get("overall_score", "0")).strip()
                            score = None
                            if score_str.isdigit():
                                score = int(score_str)
                            else:
                                first_digit = next((char for char in score_str if char.isdigit()), None)
                                if first_digit:
                                    score = int(first_digit)
                            
                            if score:
                                if difficulty not in difficulty_scores:
                                    difficulty_scores[difficulty] = []
                                difficulty_scores[difficulty].append(score)
                        
                        # Display metrics for each difficulty
                        if difficulty_scores:
                            diff_cols = st.columns(len(difficulty_scores))
                            for col_idx, (difficulty, scores_by_diff) in enumerate(sorted(difficulty_scores.items())):
                                with diff_cols[col_idx]:
                                    avg = sum(scores_by_diff) / len(scores_by_diff)
                                    st.metric(
                                        label=f"{difficulty}",
                                        value=f"{avg:.2f} / 5",
                                        delta=f"({len(scores_by_diff)} attempts)"
                                    )
                        
                        # Create comparison chart by difficulty
                        if difficulty_scores:
                            st.markdown("---")
                            st.subheader("Average Score by Difficulty")
                            
                            difficulties = sorted(difficulty_scores.keys())
                            averages = [sum(difficulty_scores[d]) / len(difficulty_scores[d]) for d in difficulties]
                            
                            fig_bar = go.Figure(data=[
                                go.Bar(
                                    x=difficulties,
                                    y=averages,
                                    marker=dict(color=['#ff7f0e', '#2ca02c', '#d62728']),
                                    text=[f"{avg:.2f}" for avg in averages],
                                    textposition='outside'
                                )
                            ])
                            
                            fig_bar.update_layout(
                                title="Average Score by Difficulty Level",
                                xaxis_title="Difficulty",
                                yaxis_title="Average Score",
                                height=400,
                                yaxis=dict(range=[0, 5])
                            )
                            
                            st.plotly_chart(fig_bar, use_container_width=True, key=f"difficulty_bar_{role_name}")

                        # Create a simplified display table
                        display_data = []
                        for res in filtered_role_results:
                            display_row = {
                                "Date": res.get("timestamp", "N/A")[:10],
                                "Name": f"{res.get('first_name', '')} {res.get('last_name', '')}" if "first_name" in res else res.get("user_name", "N/A"),
                                "Role": res.get("role", "N/A"),
                                "Difficulty": res.get("difficulty", "N/A"),
                                "Score": res.get("overall_score", "N/A")
                            }
                            display_data.append(display_row)
                        
                        st.dataframe(display_data, use_container_width=True)

                        # Expander to view full details
                        for i, result in enumerate(reversed(filtered_role_results)):
                            user_display = f"{result.get('first_name', '')} {result.get('last_name', '')}" if "first_name" in result else result.get("user_name", "N/A")
                            difficulty_display = result.get("difficulty", "N/A")
                            with st.expander(f"{result.get('timestamp', 'N/A')[:16]} - {result.get('role', 'N/A')} ({difficulty_display}) - Score: {result.get('overall_score', 'N/A')}"):
                                st.markdown(f"**User:** {user_display}")
                                st.markdown(f"**Email:** {result.get('email', 'N/A')}")
                                st.markdown(f"**Difficulty:** {difficulty_display}")
                                st.markdown("---")
                                st.markdown("#### Scenario")
                                st.info(result.get('scenario', 'N/A'))
                                st.markdown("#### User Response")
                                st.warning(result.get('user_response', 'N/A'))
                                st.markdown("#### AI Evaluation")
                                st.markdown(result.get('evaluation', 'N/A'))
                
                # Display analytics for All Roles tab
                with role_tabs[0]:
                    display_role_analytics(filtered_results, "All Roles")
                
                # Display analytics for each role-specific tab
                for idx, role in enumerate(all_roles):
                    with role_tabs[idx + 1]:
                        role_filtered = [res for res in filtered_results if res.get("role") == role]
                        display_role_analytics(role_filtered, role)
else:
    st.info("Please enter your first name, last name, and email in the sidebar, provide an API key, and click 'Login' to use the application.")
