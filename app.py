import streamlit as st
import google.genai as genai
from google.genai import types
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
ASSIGNMENTS_FILE = "scenario_assignments.json"

# --- UND Housing Context for Realistic Scenarios ---
UND_HOUSING_CONTEXT = """
RESIDENCE HALLS AT UND:
Suite Style (Shared bath between 2 rooms): McVey Hall, West Hall, Brannon Hall, Noren Hall, Selke Hall
Community Style (Shared floor bath): Smith Hall, Johnstone Hall (Smith/Johnstone complex)
Apartment Style (In-unit kitchen/bath): University Place, Swanson Hall

APARTMENT LOCATIONS:
Berkeley Drive, Carleton Court, Hamline Square, Mt. Vernon/Williamsburg, Swanson Complex, Tulane Court, Virginia Rose, 3904 University Ave

KEY POLICIES & PROCEDURES:
- Guest Policy: Max 3 consecutive nights, 6 nights total per month, must be escorted 24/7, roommate consent required
- Quiet Hours: Sun-Thu 10 PM-10 AM, Fri-Sat 12 AM-10 AM, Courtesy Hours 24/7
- Lockout Fees: $10 during business hours, $25 after hours, $75 for lost key recore
- Room Changes: Frozen first 2 weeks of semester, RD approval required, unauthorized moves incur $100+ fine
- Alcohol/Drugs: Under 21 strictly prohibited, 21+ only in all-age rooms, no paraphernalia, no empty containers under 21
- Guest Limit: Under 18 guests generally prohibited unless immediate family
- Maintenance: Routine within 2 business days via portal, emergency calls RA on Duty after hours
- Move-Out: 60-day notice required, residents must clean, $165 fine for modem removal

HOUSING CONTACT INFORMATION:
- Phone: 701.777.4251
- Email: housing@UND.edu
- Office Hours: Monday-Friday 8:00 AM - 4:30 PM
- After-Hours Emergency: Contact RA on Duty

HOUSING RATES (2025-2026):
- Residence Hall Double: $5,100-$6,180/year (varies by hall)
- Residence Hall Single: $5,900-$7,300/year
- Apartments One Bedroom: $735-$845/month
- Apartments Two Bedroom: $830-$935/month
- Apartments Three Bedroom: $1,010-$1,400/month
- Apartment utilities included: Internet, Water, Sewer, Trash (electricity separate)

IMPORTANT PROCESSES:
- First-year students required to live on campus (exemptions available)
- Housing contracts: Full academic year for halls, flexible lease terms for apartments
- Wilkerson Service Center handles mail, packages, and key checkouts
- Housing Self-Service portal for applications and requests
- Room changes based on availability offered on Wednesdays
"""

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
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_users(users_data):
    """Saves user accounts to JSON."""
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
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
        with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_results(data):
    """Saves the results to the JSON file."""
    try:
        with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        return True
    except Exception as e:
        st.error(f"Error saving results: {e}")
        return False

def load_config():
    """Loads the configuration from the JSON file."""
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
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
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=4)
        return True
    except Exception as e:
        st.error(f"Failed to save configuration: {e}")
        return False

def load_assignments():
    """Loads scenario assignments from the JSON file."""
    try:
        with open(ASSIGNMENTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"assignments": []}

def save_assignments(data):
    """Saves scenario assignments to the JSON file."""
    try:
        with open(ASSIGNMENTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        return True
    except Exception as e:
        st.error(f"Failed to save assignments: {e}")
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

def get_supervisor_visible_users(supervisor_email, users_db, org_chart):
    """
    Get all users that a supervisor can see based on org hierarchy.
    Includes direct reports and all staff below them in the chain.
    """
    visible_users = set()
    users_db_loaded = users_db if users_db else load_users()
    
    # Get all roles that this person supervises (directly or indirectly)
    def get_subordinate_roles(role_name, edges, visited=None):
        if visited is None:
            visited = set()
        if role_name in visited:
            return visited
        visited.add(role_name)
        
        for edge in edges:
            if edge.get('target') == role_name:  # This role reports to role_name
                visited.update(get_subordinate_roles(edge['source'], edges, visited))
        return visited
    
    # Find supervisor's role
    supervisor_role = None
    for email, user_data in users_db_loaded.items():
        if email == supervisor_email:
            supervisor_role = user_data.get('position')
            break
    
    if not supervisor_role:
        return visible_users
    
    # Get all roles that report to this supervisor (including indirectly)
    subordinate_roles = get_subordinate_roles(supervisor_role, org_chart.get('edges', []))
    
    # Find all users in those roles
    for email, user_data in users_db_loaded.items():
        if user_data.get('position') in subordinate_roles:
            visible_users.add(email)
    
    return visible_users

# --- Gemini API Configuration ---
def configure_genai(api_key):
    """Configures the Gemini API with the provided key."""
    try:
        # Create client with the new SDK
        st.session_state.genai_client = genai.Client(api_key=api_key)
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
                        models_pager = st.session_state.genai_client.models.list()
                        st.session_state.models = [m.name for m in models_pager if 'gemini' in m.name.lower()]
                        if not st.session_state.models:
                            # Fallback if no gemini models found
                            st.session_state.models = [
                                'models/gemini-2.0-flash-exp',
                                'models/gemini-1.5-pro',
                                'models/gemini-1.5-flash'
                            ]
                    except Exception as e:
                        # Use fallback models on error
                        st.session_state.models = [
                            'models/gemini-2.0-flash-exp',
                            'models/gemini-1.5-pro',
                            'models/gemini-1.5-flash'
                        ]
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
                            models_pager = st.session_state.genai_client.models.list()
                            st.session_state.models = [m.name for m in models_pager if 'gemini' in m.name.lower()]
                            if not st.session_state.models:
                                # Fallback if no gemini models found
                                st.session_state.models = [
                                    'models/gemini-2.0-flash-exp',
                                    'models/gemini-1.5-pro',
                                    'models/gemini-1.5-flash'
                                ]
                            # Set default model if not already set
                            if 'selected_model' not in st.session_state and st.session_state.models:
                                st.session_state.selected_model = st.session_state.models[0]
                        except Exception as e:
                            # Use fallback models on error
                            st.session_state.models = [
                                'models/gemini-2.0-flash-exp',
                                'models/gemini-1.5-pro',
                                'models/gemini-1.5-flash'
                            ]
                            st.session_state.selected_model = st.session_state.models[0]
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
            st.session_state.selected_model = 'models/gemini-2.0-flash-exp'  # Fallback default (with proper model prefix)
    
    # Use client from session state - ensure it exists
    client = st.session_state.get('genai_client')
    
    # If client is None, try to reinitialize it from the API key in secrets
    if client is None:
        api_key_secret = st.secrets.get("gemini_api_key")
        if api_key_secret:
            try:
                client = genai.Client(api_key=api_key_secret)
                st.session_state.genai_client = client
            except Exception as e:
                st.error(f"Failed to initialize API client: {e}")
                st.stop()
        else:
            st.error("API client not initialized. Please configure the API in the sidebar first.")
            st.stop()

    # Build tab list based on user role
    if st.session_state.get("is_admin"):
        tab_names = [
            "Scenario Simulator",
            "Tone Polisher",
            "Assign Scenarios",
            "Call Analysis",
            "Pending Review",
            "Guiding NORTH Framework",
            "Org Chart",
            "Configuration",
            "Results & Progress"
        ]
        tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs(tab_names)
        assign_scenarios_tab = tab3
        pending_review_tab = tab5
        framework_tab = tab6
        org_chart_tab = tab7
        config_tab = tab8
        results_tab = tab9
    else:
        # Check if user is a supervisor
        is_supervisor = len(st.session_state.get('direct_reports', [])) > 0
        
        if is_supervisor:
            tab_names = [
                "Scenario Simulator",
                "Tone Polisher",
                "Assign Scenarios",
                "Pending Review",
                "Guiding NORTH Framework",
                "Org Chart",
                "Results & Progress"
            ]
            tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(tab_names)
            assign_scenarios_tab = tab3
            pending_review_tab = tab4
            framework_tab = tab5
            org_chart_tab = tab6
            config_tab = None
            results_tab = tab7
        else:
            tab_names = [
                "Scenario Simulator",
                "Tone Polisher",
                "Assigned Scenarios",
                "Guiding NORTH Framework",
                "Org Chart",
                "Results & Progress"
            ]
            tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(tab_names)
            pending_review_tab = None
            assigned_scenarios_tab = tab3
            framework_tab = tab4
            org_chart_tab = tab5
            config_tab = None
            results_tab = tab6

    with tab1:
        st.header("Scenario Simulator")
        st.write("Practice applying the Guiding North Framework in realistic situations.")

        if not STAFF_ROLES:
             st.warning("No staff roles configured. Please add roles in the Configuration tab.")
             st.stop()

        # Staff can only practice their own role, supervisors can practice any of their direct reports' roles
        available_roles = [st.session_state.position] if st.session_state.position else list(STAFF_ROLES.keys())
        
        selected_role = st.selectbox("Select Your Role:", available_roles, key="role_selector")
        if selected_role not in STAFF_ROLES:
            st.warning("Selected role is not configured. Please update roles in the Configuration tab.")
            st.stop()
        difficulty = st.selectbox(
            "Scenario Difficulty:",
            ["Easier than average", "Average", "Harder than average"],
            key="difficulty_selector"
        )

        if "scenario" not in st.session_state:
            st.session_state.scenario = ""
        if "evaluation" not in st.session_state:
            st.session_state.evaluation = ""

        if "last_building" not in st.session_state:
            st.session_state.last_building = None
        if "building_history" not in st.session_state:
            st.session_state.building_history = []

        if st.button("🎲 Generate New Scenario", key="generate_scenario_button"):
            with st.spinner("Generating a new scenario..."):
                role_info = STAFF_ROLES.get(selected_role, {})
                last_scenario_text = st.session_state.scenario.strip() if st.session_state.scenario else "None"
                building_history_text = ", ".join(st.session_state.building_history[-5:]) if st.session_state.building_history else "None"
                
                # Build role-specific scenario guidance
                role_specific_guidance = ""
                if "Resident Director" in selected_role or "Apt RD" in selected_role or "RD" in selected_role:
                    role_specific_guidance = """
                    
                    **Role-Specific Scenario Focus:**
                    As a Resident Director, you handle a wide range of residential life issues. Ensure variety across these common scenario types:
                    - Student conduct and policy enforcement situations
                    - Roommate mediation and conflict resolution
                    - Emergency and safety concerns
                    - Mental health and wellness referrals
                    - Community development and staff supervision
                    - Residential community issues and building management
                    - Student concerns and complaints
                    - Staffing and RA coordination challenges
                    
                    Vary between these types systematically to build comprehensive competency.
                    """
                
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
                {role_specific_guidance}

                **UND Housing Information (Use to Make Scenarios Realistic):**
                ---
                {UND_HOUSING_CONTEXT}
                ---

                **Task:** Based *only* on the framework document provided, generate a single, detailed, and realistic scenario for a '{selected_role}'.
                
                **Critical Requirements:**
                1. **Difficulty Level:** {difficulty}
                2. **Student Name:** Use a diverse, realistic first name that is NOT the same as in the previous scenario. Choose from diverse names like: Alex, Jordan, Casey, Morgan, Avery, Quinn, Jamie, Riley, Taylor, Chris, Sam, Pat, Blake, Drew, Devon, or create another realistic diverse name. Ensure the name changes every time.
                3. **UND Housing Realism:** 
                   - Reference specific UND residence halls (McVey, West, Brannon, Noren, Selke, Smith, Johnstone, University Place, Swanson) or apartments (Berkeley Drive, Carleton Court, Hamline Square, etc.)
                   - Include real UND policies (quiet hours, guest limits, alcohol rules, lockout fees, room change procedures, maintenance protocols)
                   - Use authentic fee amounts ($10/$25 lockout fees, $75 key recore, $100+ unauthorized move fines, $165 modem fine, $5,100-$6,180 annual hall costs, apartment rates)
                   - Reference real resources (Wilkerson Service Center, Housing Self-Service portal, RA on Duty)
                   - Make scenarios feel like actual situations at UND Housing & Residence Life
                4. **Variety Requirement:** Do NOT repeat the same type of scenario as the previous one. Focus on different residential life issues.
                5. **Building/Location Variety:** IMPORTANT - Do NOT repeat the same building as the previous scenario. Vary buildings across all available options:
                   - Residence Halls: McVey Hall, West Hall, Brannon Hall, Noren Hall, Selke Hall, Smith Hall, Johnstone Hall, University Place, Swanson Hall
                   - Apartments: Berkeley Drive, Carleton Court, Hamline Square, Mt. Vernon/Williamsburg, Swanson Complex, Tulane Court, Virginia Rose, 3904 University Ave
                   - Each scenario should use a DIFFERENT building/location from the previous scenario to ensure comprehensive campus coverage
                6. **Scenario Type:** Pick from these areas (rotate through them, avoiding the previous type):
                   - Roommate mediation and conflict resolution
                   - Student conduct violations (noise, guests, quiet hours, alcohol/substance concerns)
                   - Mental health concerns and wellness referrals
                   - Emergency/safety situations
                   - Key and electronic door access issues (lockouts, card access failures, lost keys)
                   - Community development and RA team issues
                   - Academic or financial concerns affecting housing
                   - Bias incidents or community safety concerns
                   - Building maintenance or facility issues
                   - Housing reassignment or room change requests
                   - Policy clarification and resident concerns
                   - Staff or student complaints

                **Previous Scenario Details (for diversity checking only):**
                {last_scenario_text}

                **Recent Building Locations Used (avoid repeating these):**
                {building_history_text}

                **CRITICAL - Building Selection Instructions:**
                You MUST select a building/location that has NOT been used in recent scenarios. The scenario MUST mention the specific building name (e.g., "In McVey Hall," "At Berkeley Drive Apartments," etc.). Each new scenario must use a different building to ensure comprehensive coverage of all UND Housing locations.

                The scenario should be a full, detailed paragraph that is realistic and something this person would likely encounter in their role at UND Housing. It must be designed to test their proficiency in one or more pillars of the Guiding NORTH framework. Include the student's name, specific details, and contextual information to make it engaging and appropriately challenging for the selected difficulty level.
                """
                try:
                    response = client.models.generate_content(
                        model=st.session_state.selected_model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            temperature=0.9,
                            max_output_tokens=15000
                        )
                    )
                    st.session_state.scenario = response.text
                    st.session_state.evaluation = "" # Clear previous evaluation
                except Exception as e:
                    st.error(f"Error generating scenario: {e}")
                
                # Extract and track building name from scenario
                if st.session_state.scenario:
                    import re
                    buildings = [
                        "McVey Hall", "West Hall", "Brannon Hall", "Noren Hall", "Selke Hall",
                        "Smith Hall", "Johnstone Hall", "University Place", "Swanson Hall",
                        "Berkeley Drive", "Carleton Court", "Hamline Square", "Mt. Vernon",
                        "Williamsburg", "Swanson Complex", "Tulane Court", "Virginia Rose", "3904 University Ave"
                    ]
                    for building in buildings:
                        if building in st.session_state.scenario:
                            if building not in st.session_state.building_history:
                                st.session_state.building_history.append(building)
                            break

        if st.session_state.scenario:
            st.info(f"**Your Scenario:**\n\n{st.session_state.scenario}")
            
            user_response = st.text_area("Your Response:", height=150, key="response_input")

            if st.button("📤 Submit Response to Supervisor", key="evaluate_response_button"):
                if user_response:
                    with st.spinner("Submitting your response for supervisor review..."):
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
                        1. Provide an 'Overall Score' from 1 (Needs Improvement) to 4 (Exemplary).
                        2. For each of the five pillars (N, O, R, T, H), assign a rating (Needs Development, Proficient, or Exemplary) and provide a brief justification for your rating, citing specific examples from the user's response. 
                        3. Conclude with a full, detailed 'Exemplary Response Example' that demonstrates how a top-performing staff member would have handled the interaction from start to finish.

                        **Output Format (Strict):**
                        ### Guiding NORTH Evaluation:

                        OVERALL_SCORE: [Your 1-4 Rating]

                        **Overall Score:** [Your 1-4 Rating]

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
                            evaluation_response = client.models.generate_content(
                                model=st.session_state.selected_model,
                                contents=eval_prompt,
                                config=types.GenerateContentConfig(
                                    temperature=0.5,
                                    max_output_tokens=15000
                                )
                            )
                            # Extract the evaluation text (don't show to staff)
                            evaluation_text = evaluation_response.text
                            
                            # Extract overall score from the evaluation text
                            overall_score = "Not Found"
                            for line in evaluation_text.splitlines():
                                if "Overall Score:" in line:
                                    try:
                                        overall_score = line.split(":")[1].strip()
                                    except IndexError:
                                        overall_score = "Parse Error"
                                    break
                            
                            # Save the result directly to pending review (without showing to staff)
                            results = load_results()
                            new_result = {
                                "first_name": st.session_state.first_name,
                                "last_name": st.session_state.last_name,
                                "email": st.session_state.email,
                                "timestamp": datetime.now().isoformat(),
                                "role": selected_role,
                                "difficulty": difficulty,
                                "scenario": st.session_state.scenario,
                                "user_response": user_response,
                                "evaluation": evaluation_text,
                                "overall_score": overall_score,
                                "status": "pending",
                                "reviewed_by": None,
                                "review_date": None,
                                "supervisor_notes": ""
                            }
                            results.append(new_result)
                            if save_results(results):
                                st.success("✅ Response submitted to your supervisor for review!")
                                st.info("🤝 Your supervisor will review your response and schedule a meeting to discuss the feedback and suggestions.")
                                st.session_state.scenario = ""
                                st.session_state.evaluation = ""
                                st.rerun()
                            else:
                                st.error("Failed to submit your response.")
                        except Exception as e:
                            st.error(f"Error submitting response: {e}")
                else:
                    st.warning("Please enter your response before submitting.")

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
                        # This assumes 'client' is defined and configured earlier, e.g., in the sidebar
                        if st.session_state.get('selected_model') and st.session_state.api_configured:
                            polished_response = client.models.generate_content(
                                model=st.session_state.selected_model,
                                contents=polish_prompt,
                                config=types.GenerateContentConfig(
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
        with tab4:
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
                            1. Provide an 'Overall Score' from 1 (Needs Improvement) to 4 (Exemplary).
                            2. For each of the five pillars (N, O, R, T, H), assign a rating (Needs Development, Proficient, or Exemplary) and provide a brief justification for your rating, citing specific examples from the call transcript.
                            3. Provide specific suggestions for improvement where applicable.
                            4. Conclude with a full, detailed 'Exemplary Call Example' that demonstrates how a top-performing staff member would have handled the call from start to finish.

                            **Output Format (Strict):**
                            ### Guiding NORTH Evaluation:

                            OVERALL_SCORE: [Your 1-4 Rating]

                            **Overall Score:** [Your 1-4 Rating]

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
                                if st.session_state.get('selected_model') and st.session_state.api_configured:
                                    analysis_response = client.models.generate_content(
                                        model=st.session_state.selected_model,
                                        contents=analysis_prompt,
                                        config=types.GenerateContentConfig(
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
                        call_first_name_clean = (call_first_name or "").strip()
                        call_last_name_clean = (call_last_name or "").strip()
                        if call_first_name_clean and call_last_name_clean:
                            with st.spinner("Processing audio and analyzing call..."):
                                try:
                                    # Prepare audio part with explicit mime type
                                    import mimetypes
                                    audio_bytes = uploaded_audio.getvalue()
                                    mime_type = uploaded_audio.type or mimetypes.guess_type(uploaded_audio.name)[0] or "audio/mpeg"
                                    audio_part = types.Part.from_bytes(
                                        data=audio_bytes,
                                        mime_type=mime_type
                                    )
                                    
                                    role_info = STAFF_ROLES.get(call_role, {})
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
                                    3. Provide an 'Overall Score' from 1 (Needs Improvement) to 4 (Exemplary).
                                    4. For each of the five pillars (N, O, R, T, H), assign a rating (Needs Development, Proficient, or Exemplary) and provide a brief justification for your rating, citing specific examples from the call.
                                    5. Provide specific suggestions for improvement where applicable.
                                    6. Conclude with a full, detailed 'Exemplary Call Example' that demonstrates how a top-performing staff member would have handled the call from start to finish.

                                    **Output Format (Strict):**
                                    ### Call Transcript:
                                    [Full transcript of the call]

                                    ---

                                    ### Guiding NORTH Evaluation:

                                    OVERALL_SCORE: [Your 1-4 Rating]

                                    **Overall Score:** [Your 1-4 Rating]

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
                                        analysis_response = client.models.generate_content(
                                            model=st.session_state.selected_model,
                                            contents=[audio_part, analysis_prompt],
                                            config=types.GenerateContentConfig(
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
                            st.warning("Please provide your first and last name before analyzing the call.")

    # Assign Scenarios Tab - For Supervisors Only
    if 'assign_scenarios_tab' in locals() and assign_scenarios_tab is not None:
        with assign_scenarios_tab:
            st.header("📤 Assign Scenarios to Staff")
            st.write("Create and assign targeted training scenarios to your team members based on specific topics.")
            
            # Get supervisor's direct and indirect reports (roles)
            def get_subordinate_roles(role_name, edges, visited=None):
                if visited is None:
                    visited = set()
                if role_name in visited:
                    return visited
                visited.add(role_name)

                for edge in edges:
                    if edge.get('target') == role_name:
                        visited.update(get_subordinate_roles(edge['source'], edges, visited))
                return visited

            if st.session_state.get("is_admin"):
                report_roles = list(STAFF_ROLES.keys())
            else:
                supervisor_role = st.session_state.get("position")
                report_roles = list(get_subordinate_roles(supervisor_role, ORG_CHART.get('edges', [])))

            if not report_roles:
                st.warning("You don't have any reports to assign scenarios to.")
            else:
                # Create two columns for layout
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("Select Recipients")
                    selected_role = st.selectbox(
                        "Select a role:",
                        options=sorted(report_roles),
                        key="assign_scenario_role"
                    )

                    users_db_for_assign = load_users()
                    staff_in_role = {
                        email: f"{user.get('first_name', '').strip()} {user.get('last_name', '').strip()}".strip()
                        for email, user in users_db_for_assign.items()
                        if user.get('position') == selected_role
                    }
                    staff_options = [
                        f"{name} ({email})" if name else email
                        for email, name in staff_in_role.items()
                    ]
                    staff_options.sort()

                    if not staff_options:
                        st.info("No staff accounts found for this role.")
                        selected_staff = []
                    else:
                        selected_staff_labels = st.multiselect(
                            "Choose staff members to receive the scenario:",
                            options=staff_options,
                            key="assign_scenario_staff"
                        )
                        selected_staff = [
                            label.split("(")[-1].rstrip(")")
                            for label in selected_staff_labels
                        ]
                    
                with col2:
                    st.subheader("Scenario Topic")
                    scenario_topics = [
                        "Housing Application",
                        "Room Assignment",
                        "Roommate Matching",
                        "Roommate Conflict",
                        "Noise Complaint",
                        "Housing Policy Question",
                        "Maintenance Request",
                        "Key & Electronic Access Issue",
                        "Room Change Request",
                        "Lease Violation",
                        "Guest Policy Issue",
                        "Parking Problem",
                        "Meeting Room Reservation",
                        "Billing Question",
                        "Community Standards",
                        "Student Wellness Concern"
                    ]
                    selected_topic = st.selectbox(
                        "Select the topic for the scenario:",
                        options=scenario_topics,
                        key="assign_scenario_topic"
                    )
                    
                    contact_type = st.selectbox(
                        "Type of Customer Contact:",
                        ["Email", "In Person Question", "Phone Call", "On-Call Situation"],
                        key="assign_scenario_contact_type"
                    )
                
                # Generate scenario button
                if st.button("Generate and Assign Scenario", key="generate_assign_scenario_btn"):
                    if not selected_staff:
                        st.error("Please select at least one staff member.")
                    else:
                        with st.spinner(f"Generating {selected_topic} scenario for {len(selected_staff)} staff member(s)..."):
                            try:
                                # Generate the scenario
                                scenario_prompt = f"""Generate a realistic housing and residence life training scenario for the role: {selected_role}.

SCENARIO REQUIREMENTS:
Topic: {selected_topic}
Contact Type: {contact_type}

USE THIS AUTHENTIC UND HOUSING INFORMATION:
{UND_HOUSING_CONTEXT}

The scenario should:
- Be presented as a {contact_type} (format the scenario appropriately for this contact method)
- Reference real UND residence halls (McVey, West, Brannon, Noren, Selke, Smith, Johnstone, University Place, Swanson) or apartments (Berkeley Drive, Carleton Court, Hamline Square, etc.)
- Include authentic UND policies on quiet hours, guest limits, alcohol, lockouts, room changes, maintenance procedures
- Use realistic fee amounts ($10/$25 lockout fees, $75 key recore, $100+ unauthorized move fine, $165 modem removal fine)
- Reference actual housing rates or the Wilkerson Service Center
- Include specific times, dates, and building details to make it immersive
- Feature real student scenarios a {selected_role} would actually handle
- Require the staff member to apply the Guiding North Framework principles
- Be appropriate for role-playing or discussion
- Be tailored to the responsibilities and perspective of a {selected_role}
- Include all relevant context woven into the scenario (no separate context section)
- Use ALL available residence halls and apartments: Vary the location across McVey Hall, West Hall, Brannon Hall, Noren Hall, Selke Hall, Smith Hall, Johnstone Hall, University Place, Swanson Hall, Berkeley Drive, Carleton Court, Hamline Square, Mt. Vernon/Williamsburg, Swanson Complex, Tulane Court, Virginia Rose, and 3904 University Ave

Format:
SCENARIO TITLE: [Realistic, specific title]
SITUATION: [Detailed scenario with all relevant context included - mention specific building, time, fees, policies, student names if applicable]
YOUR TASK: [What the {selected_role} should do to handle this situation]

CRITICAL: Do NOT end the scenario with any sentence explaining why it is difficult, complex, or what makes it a {contact_type} scenario. Do not include sentences like "This scenario is harder than average because..." or "This scenario tests..." or "This scenario requires...". Present ONLY the scenario and task - nothing more."""

                                # Call Gemini API (use configured client)
                                client = st.session_state.get('genai_client')
                                if not client:
                                    st.error("Gemini API is not configured. Please initialize it in the sidebar.")
                                    st.stop()

                                response = client.models.generate_content(
                                    model=st.session_state.get("selected_model", "models/gemini-1.5-flash"),
                                    contents=scenario_prompt
                                )
                                
                                generated_scenario = response.text if response.text else "Unable to generate scenario"
                                
                                # Remove any meta-commentary about difficulty if it still appears
                                # Look for sentences starting with "This scenario is" that explain difficulty
                                import re
                                generated_scenario = re.sub(
                                    r'\n*This scenario is (?:harder|easier|more|less) than average because.*?(?=\n|$)',
                                    '',
                                    generated_scenario,
                                    flags=re.IGNORECASE | re.DOTALL
                                )
                                # Also remove any other meta-commentary patterns
                                generated_scenario = re.sub(
                                    r'\n*This scenario (?:tests|requires|challenges|involves).*?(?=\n|$)',
                                    '',
                                    generated_scenario,
                                    flags=re.IGNORECASE | re.DOTALL
                                )
                                
                                # Save the assignment
                                assignments_data = load_assignments()
                                
                                for staff_email in selected_staff:
                                    user_data = load_users().get(staff_email, {})
                                    assignment = {
                                        "id": f"{int(datetime.now().timestamp())}_{staff_email}",
                                        "supervisor_email": st.session_state.get("email"),
                                        "supervisor_name": f"{st.session_state.get('first_name')} {st.session_state.get('last_name')}",
                                        "staff_email": staff_email,
                                        "staff_name": f"{user_data.get('first_name', 'Staff')} {user_data.get('last_name', 'Member')}".strip(),
                                        "assigned_role": selected_role,
                                        "staff_position": user_data.get('position', selected_role),
                                        "topic": selected_topic,
                                        "scenario": generated_scenario,
                                        "assigned_date": datetime.now().isoformat(),
                                        "completed": False,
                                        "response": None,
                                        "response_date": None
                                    }
                                    assignments_data["assignments"].append(assignment)
                                
                                if save_assignments(assignments_data):
                                    st.success(f"✅ Scenario assigned to {len(selected_staff)} staff member(s)!")
                                    st.info("They will see the scenario in their \"Assigned Scenarios\" section.")
                                else:
                                    st.error("Failed to save the assignment.")
                                    
                            except Exception as e:
                                st.error(f"Error generating scenario: {e}")

    # Pending Review Tab - For Supervisors Only
    if pending_review_tab is not None:
        with pending_review_tab:
            st.header("📋 Pending Scenario Reviews")
            st.write("Review and approve scenario submissions from your staff before they see the results.")
            
            if st.session_state.get("is_admin"):
                st.info("👮 Admin view: You can see all pending scenarios from all staff members.")
                visible_users = {user_email for user_email in load_users().keys()}
            else:
                st.info("👥 Supervisor view: You can see pending scenarios from your direct reports.")
                visible_users = get_supervisor_visible_users(
                    st.session_state.email, 
                    load_users(), 
                    ORG_CHART
                )
            
            # Load results and filter for pending
            all_results = load_results()
            pending_results = [
                (idx, r) for idx, r in enumerate(all_results) 
                if r.get('status') == 'pending' and r.get('email') in visible_users
            ]

            # Load assigned scenarios and filter for pending review
            assignments_data = load_assignments()
            pending_assignments = [
                (idx, a) for idx, a in enumerate(assignments_data.get("assignments", []))
                if a.get("completed")
                and not a.get("reviewed")
                and a.get("staff_email") in visible_users
            ]
            
            if not pending_results and not pending_assignments:
                st.success("✅ All scenarios have been reviewed!")
            else:
                pending_count = len(pending_results) + len(pending_assignments)
                st.warning(f"⚠️ {pending_count} scenarios pending your review")
                
                for idx, result in pending_results:
                    with st.expander(
                        f"📝 {result.get('first_name')} {result.get('last_name')} - {result.get('role')} ({result.get('difficulty')})",
                        expanded=False
                    ):
                        col1, col2 = st.columns([1, 1])
                        
                        with col1:
                            st.markdown(f"**Name:** {result.get('first_name')} {result.get('last_name')}")
                            st.markdown(f"**Email:** {result.get('email')}")
                            st.markdown(f"**Role:** {result.get('role')}")
                            st.markdown(f"**Difficulty:** {result.get('difficulty')}")
                            st.markdown(f"**Submitted:** {result.get('timestamp', 'N/A')[:16]}")
                        
                        with col2:
                            st.markdown(f"**Overall Score:** {result.get('overall_score', 'N/A')}")
                            st.markdown(f"**Status:** Pending Review")
                        
                        st.divider()
                        
                        st.subheader("📋 Scenario")
                        st.info(result.get('scenario', 'N/A'))
                        
                        st.subheader("✍️ Staff Response")
                        st.warning(result.get('user_response', 'N/A'))
                        
                        st.subheader("🔍 AI Evaluation")
                        st.markdown(result.get('evaluation', 'N/A'))
                        
                        st.divider()
                        
                        st.subheader("Supervisor Review")
                        supervisor_notes = st.text_area(
                            "Add supervisor notes (optional):",
                            value=result.get('supervisor_notes', ''),
                            height=100,
                            key=f"notes_{idx}_{result.get('email')}"
                        )
                        
                        col_approve, col_reject = st.columns(2)
                        
                        with col_approve:
                            if st.button("✅ Mark as Reviewed", key=f"approve_{idx}_{result.get('email')}", type="primary"):
                                # Update the result
                                all_results[idx]['status'] = 'completed'
                                all_results[idx]['reviewed_by'] = st.session_state.email
                                all_results[idx]['review_date'] = datetime.now().isoformat()
                                all_results[idx]['supervisor_notes'] = supervisor_notes
                                
                                if save_results(all_results):
                                    st.success(f"✅ Scenario marked as reviewed!")
                                    st.rerun()
                                else:
                                    st.error("Failed to update scenario status.")

                if pending_assignments:
                    st.divider()
                    st.subheader("📧 Assigned Scenarios Pending Review")

                    for idx, assignment in pending_assignments:
                        staff_display = assignment.get("staff_name") or assignment.get("staff_email")
                        assigned_date = assignment.get("assigned_date", "N/A")[:10]
                        with st.expander(
                            f"📌 {staff_display} - {assignment.get('topic')} (Assigned {assigned_date})",
                            expanded=False
                        ):
                            st.markdown(f"**Staff Email:** {assignment.get('staff_email', 'N/A')}")
                            st.markdown(f"**Topic:** {assignment.get('topic', 'N/A')}")
                            st.markdown(f"**Assigned By:** {assignment.get('supervisor_name', 'N/A')}")
                            st.markdown(f"**Submitted:** {assignment.get('response_date', 'N/A')[:16]}")

                            st.subheader("📋 Scenario")
                            st.info(assignment.get("scenario", "N/A"))

                            st.subheader("✍️ Staff Response")
                            st.warning(assignment.get("response", "N/A"))

                            if assignment.get("ai_analysis"):
                                st.subheader("🔍 AI Analysis")
                                st.markdown(assignment.get("ai_analysis", "N/A"))

                            st.subheader("Supervisor Review")
                            supervisor_feedback = st.text_area(
                                "Add supervisor feedback (optional):",
                                value=assignment.get("supervisor_feedback", ""),
                                height=100,
                                key=f"assign_feedback_{idx}_{assignment.get('staff_email')}"
                            )

                            if st.button("✅ Mark Assigned Scenario as Reviewed", key=f"assign_review_{idx}_{assignment.get('staff_email')}"):
                                assignments_data_updated = load_assignments()
                                if 0 <= idx < len(assignments_data_updated.get("assignments", [])):
                                    assignments_data_updated["assignments"][idx]["reviewed"] = True
                                    assignments_data_updated["assignments"][idx]["reviewed_by"] = st.session_state.email
                                    assignments_data_updated["assignments"][idx]["review_date"] = datetime.now().isoformat()
                                    assignments_data_updated["assignments"][idx]["supervisor_feedback"] = supervisor_feedback

                                    if save_assignments(assignments_data_updated):
                                        st.success("✅ Assigned scenario marked as reviewed!")
                                        st.rerun()
                                    else:
                                        st.error("Failed to update assigned scenario status.")

    # Assigned Scenarios Tab - For Staff Only
    if 'assigned_scenarios_tab' in locals() and assigned_scenarios_tab is not None:
        with assigned_scenarios_tab:
            st.header("📧 Assigned Training Scenarios")
            st.write("Complete the training scenarios assigned to you by your supervisor.")
            
            # Load assignments for this staff member
            assignments_data = load_assignments()
            staff_email = st.session_state.get("email")
            staff_role = st.session_state.get("position")
            
            # Filter assignments for this staff member
            my_assignments = [
                a for a in assignments_data.get("assignments", [])
                if a.get("staff_email") == staff_email
            ]
            
            if not my_assignments:
                st.info("No assigned scenarios yet. Check back soon for new training assignments from your supervisor!")
            else:
                # Tabs for pending and completed
                pending_tab, completed_tab = st.tabs(["Pending", "Completed"])
                
                with pending_tab:
                    pending_assignments = [a for a in my_assignments if not a.get("completed", False)]
                    
                    if not pending_assignments:
                        st.info("All assigned scenarios completed!")
                    else:
                        for assignment in pending_assignments:
                            with st.expander(f"📋 {assignment.get('topic')} (Assigned by {assignment.get('supervisor_name')}) - {assignment.get('assigned_date', 'Unknown')[:10]}"):
                                st.markdown("### Scenario:")
                                st.markdown(assignment.get("scenario", "No scenario text"))
                                
                                st.markdown("---")
                                st.markdown("### Your Response:")
                                response_text = st.text_area(
                                    "Describe how you would handle this scenario:",
                                    value=assignment.get("response", ""),
                                    height=200,
                                    key=f"assignment_response_{assignment.get('id')}"
                                )
                                
                                col1, col2 = st.columns(2)
                                with col1:
                                    if st.button("Submit Response", key=f"submit_assignment_{assignment.get('id')}"):
                                        if response_text.strip():
                                            with st.spinner("Analyzing your response..."):
                                                try:
                                                    # Generate AI analysis
                                                    client = st.session_state.get('genai_client')
                                                    if not client:
                                                        st.error("AI analysis not available. Response saved but not analyzed.")
                                                        analysis = "Analysis not available"
                                                    else:
                                                        analysis_prompt = f"""Evaluate this response to a housing and residence life training scenario using the Guiding North Framework pillars:

**Scenario:**
{assignment.get('scenario', 'N/A')}

**Staff Response:**
{response_text}

**Framework Pillars:**
- N (Navigate): Understand needs and root causes
- O (Own): Take responsibility for resolution
- R (Respond): Communicate professionally and respectfully
- T (Timely): Act within appropriate timeframes
- H (Help): Provide comprehensive support

Please provide:
1. Strengths of the response
2. Areas for improvement
3. Overall assessment using the rubric: Needs Development (1) | Proficient (3) | Exemplary (4)
4. Specific recommendations for growth
5. A single line exactly in this format: OVERALL_SCORE: X (where X is 1-4)

Be constructive and supportive in your evaluation."""

                                                        response = client.models.generate_content(
                                                            model=st.session_state.get("selected_model", "models/gemini-1.5-flash"),
                                                            contents=analysis_prompt
                                                        )
                                                        analysis = response.text if response.text else "Unable to analyze response"

                                                    # Update assignment with response and analysis
                                                    assignments_data_updated = load_assignments()
                                                    for idx, a in enumerate(assignments_data_updated.get("assignments", [])):
                                                        if a.get("id") == assignment.get("id"):
                                                            assignments_data_updated["assignments"][idx]["response"] = response_text
                                                            assignments_data_updated["assignments"][idx]["response_date"] = datetime.now().isoformat()
                                                            assignments_data_updated["assignments"][idx]["completed"] = True
                                                            assignments_data_updated["assignments"][idx]["ai_analysis"] = analysis
                                                            break

                                                    if save_assignments(assignments_data_updated):
                                                        st.success("✅ Response submitted and analyzed! Your supervisor will review it soon.")
                                                        st.rerun()
                                                    else:
                                                        st.error("Failed to save response.")
                                                except Exception as e:
                                                    st.error(f"Error analyzing response: {e}")
                                        else:
                                            st.warning("Please enter your response.")
                                
                                with col2:
                                    if st.button("Delete Assignment", key=f"delete_assignment_{assignment.get('id')}"):
                                        assignments_data_updated = load_assignments()
                                        assignments_data_updated["assignments"] = [
                                            a for a in assignments_data_updated.get("assignments", [])
                                            if a.get("id") != assignment.get("id")
                                        ]
                                        if save_assignments(assignments_data_updated):
                                            st.success("Assignment removed.")
                                            st.rerun()
                
                with completed_tab:
                    completed_assignments = [a for a in my_assignments if a.get("completed", False)]
                    
                    if not completed_assignments:
                        st.info("No completed scenarios yet.")
                    else:
                        for assignment in completed_assignments:
                            with st.expander(f"✅ {assignment.get('topic')} (Completed on {assignment.get('response_date', 'Unknown')[:10]})"):
                                st.markdown("### Scenario:")
                                st.markdown(assignment.get("scenario", "No scenario text"))
                                
                                st.markdown("---")
                                st.markdown("### Your Response:")
                                st.markdown(assignment.get("response", "No response"))

                                if assignment.get("ai_analysis"):
                                    st.markdown("---")
                                    st.markdown("### AI Analysis:")
                                    st.markdown(assignment.get("ai_analysis", "No analysis"))
                                
                                if assignment.get("supervisor_feedback"):
                                    st.markdown("---")
                                    st.markdown("### Supervisor Feedback:")
                                    st.info(assignment.get("supervisor_feedback"))

    # Guiding NORTH Framework Tab - Available to All Users
    with framework_tab:
        st.header("🧭 Guiding NORTH Framework")
        st.write("The comprehensive communication standard for UND Housing & Residence Life.")
        
        st.markdown("---")
        
        # Framework Overview
        st.subheader("📖 The Five Pillars")
        
        col1, col2 = st.columns(2)
        
        with col1:
            with st.expander("🎯 N - Navigate Needs", expanded=True):
                st.markdown("""
                **Listen & Understand**
                
                Listen first to understand the real issue, not just the surface question.
                
                **Key Behaviors:**
                - Ask clarifying questions
                - Validate feelings/perspective first
                - Explain the "why" behind policies
                """)
            
            with st.expander("🤝 O - Own the Outcome"):
                st.markdown("""
                **Responsibility & Resolution**
                
                Take personal responsibility for getting the student to their destination.
                
                **Key Behaviors:**
                - The receiver owns the inquiry until resolved
                - Warm handoffs only (no bouncing)
                - Follow up to confirm resolution
                """)
            
            with st.expander("💬 R - Respond Respectfully"):
                st.markdown("""
                **Tone & Professionalism**
                
                Tone and language build trust and confidence.
                
                **Key Behaviors:**
                - Warm, professional, solution-focused tone
                - No jargon (speak plainly)
                - Maintain composure during conflict
                """)
        
        with col2:
            with st.expander("⏱️ T - Timely & Truthful"):
                st.markdown("""
                **Swift & Reliable**
                
                Guidance is swift and reliable.
                
                **Key Behaviors:**
                - 24-hour response rule
                - Verify accuracy before speaking (Single Source of Truth)
                - Honesty about delays
                """)
            
            with st.expander("🚀 H - Help Proactively"):
                st.markdown("""
                **Anticipate & Prepare**
                
                Anticipate the terrain ahead and clear the path.
                
                **Key Behaviors:**
                - Clarify "next steps"
                - Use FAQs/Guides
                - Identify systemic improvements
                """)
        
        st.markdown("---")
        
        # Evaluation Rubric
        st.subheader("📊 Evaluation Rubric")
        st.write("How responses are evaluated in the Scenario Simulator:")
        
        rubric_data = {
            "Pillar": ["N - Navigate", "O - Own", "R - Respond", "T - Timely", "H - Help"],
            "Needs Development (1)": [
                "Jumps to conclusions; ignores feelings",
                "Blind transfers; 'not my job' attitude",
                "Abrupt, dismissive tone; uses jargon",
                "Misses 24h deadline; inaccurate info",
                "Focuses only on immediate query"
            ],
            "Proficient (3)": [
                "Asks clarifying questions; validates perspective",
                "Takes ownership until resolved/handed off",
                "Professional, patient tone; clear language",
                "Meets 24h deadline; accurate/verified info",
                "Clarifies next steps; uses guides/FAQs"
            ],
            "Exemplary (4)": [
                "Anticipates unstated needs; defuses tension",
                "Proactively resolves future issues",
                "Exceptional warmth; transforms negatives",
                "Immediate response; anticipates delays",
                "Creates new resources; comprehensive roadmap"
            ]
        }
        
        import pandas as pd
        df = pd.DataFrame(rubric_data)
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        st.markdown("---")
        
        # Operational Context
        st.subheader("ℹ️ Key Policies & Context")
        
        col_a, col_b = st.columns(2)
        
        with col_a:
            st.markdown("""
            **Hours of Operation:**
            - Monday-Friday: 8:00 AM - 10:00 PM
            - Saturday-Sunday: 12:00 PM - 10:00 PM
            
            **After Hours Protocol:**
            - Voicemails after 10 PM reviewed next morning
            - Staff not expected to answer at 3 AM
            - Must acknowledge delay next morning
            """)
        
        with col_b:
            st.markdown("""
            **Common Fees:**
            - Lockout Fee: $10 (business hours), $25 (after hours)
            - Lost Keys: $75 core change fee
            
            **Room Changes:**
            - 2-week freeze period at semester start
            - No moves allowed during freeze
            """)
        
        st.info("💡 **Pro Tip:** Use this framework when responding to scenarios in the Simulator tab. Your responses will be evaluated based on these pillars!")

    with org_chart_tab:
        st.header("Organizational Chart")
        st.write("Visualizing the reporting structure of your department.")

        st.subheader("Display Settings")
        chart_width = st.slider("Chart Width (px)", min_value=600, max_value=1800, value=1200, step=50)
        chart_height = st.slider("Chart Height (px)", min_value=400, max_value=1400, value=700, step=50)

        # Reload latest config for org chart display
        latest_config = load_config()
        display_org_chart = latest_config.get('org_chart', {'nodes': [], 'edges': []})
        display_staff_roles = latest_config.get('staff_roles', {})
        
        # Update nodes from staff roles (but DON'T save automatically)
        display_org_chart['nodes'] = list(display_staff_roles.keys())

        # Build role -> names mapping (supports multiple people per role)
        users_db_for_chart = load_users()
        role_to_names = {}
        for email, user_data in users_db_for_chart.items():
            role = user_data.get("position")
            if not role:
                continue
            name = f"{user_data.get('first_name', '').strip()} {user_data.get('last_name', '').strip()}".strip()
            if not name:
                name = email
            role_to_names.setdefault(role, []).append(name)

        if not display_org_chart['nodes']:
            st.warning("No staff roles defined. Please add roles in the Configuration tab to build the chart.")
        else:
            nodes = []
            for role in display_org_chart['nodes']:
                names = role_to_names.get(role, [])
                if names:
                    names_sorted = sorted(names)
                    label = f"{role}\n" + "\n".join(names_sorted)
                else:
                    label = role
                nodes.append(Node(id=role, label=label, size=25))
            edges = [Edge(source=edge['source'], target=edge['target'], label="reports to") for edge in display_org_chart.get('edges', [])]
            
            agraph_config = Config(
                width=chart_width, 
                height=chart_height, 
                directed=True, 
                physics=False,  # Disable physics for fixed positions
                hierarchical=True,  # Enable hierarchical layout for org charts
                nodeHighlightBehavior=True,
                highlightColor="#F7A7A6",
                collapsible=True,
                layout={
                    'hierarchical': {
                        'enabled': True,
                        'levelSeparation': 150,
                        'nodeSpacing': 200,
                        'treeSpacing': 200,
                        'blockShifting': True,
                        'edgeMinimization': True,
                        'parentCentralization': True,
                        'direction': 'DU',  # Down-Up (managers at top, staff at bottom)
                        'sortMethod': 'directed'  # Sort by hierarchy
                    }
                }
            )

            agraph(nodes=nodes, edges=edges, config=agraph_config)


    # Configuration Tab - Admin Only
    if st.session_state.get("is_admin"):
        with config_tab:
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
                    # Reload config to ensure we have the latest state
                    current_config = load_config()
                    current_staff_roles = current_config.get("staff_roles", {})
                    
                    if new_role_name and new_role_name not in current_staff_roles:
                        current_staff_roles[new_role_name] = {
                            "description": "Please upload a PDF job description below.",
                            "system_instruction": f"You are a practice partner for a {new_role_name}. Evaluate responses based on their job description and the Guiding North Framework."
                        }
                        current_config["staff_roles"] = current_staff_roles
                        if save_config(current_config):
                            st.success(f"Role '{new_role_name}' added to chart and roles list!")
                            st.rerun()
                        else:
                            st.error("Failed to save the new role.")
                    else:
                        if not new_role_name:
                            st.error("Role name cannot be empty.")
                        else:
                            st.error(f"Role '{new_role_name}' already exists.")

                # Reload STAFF_ROLES to get latest from disk
                current_config = load_config()
                display_staff_roles = current_config.get("staff_roles", {})
                current_org_chart = current_config.get("org_chart", {'nodes': [], 'edges': []})
                
                if not display_staff_roles or len(display_staff_roles) < 2:
                    st.info("You need at least two roles to define a reporting structure.")
                else:
                    role_names = list(display_staff_roles.keys())
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
                                if new_edge not in current_org_chart.get('edges', []):
                                    current_org_chart.setdefault('edges', []).append(new_edge)
                                    current_config['org_chart'] = current_org_chart
                                    if save_config(current_config):
                                        st.success(f"Added: {subordinate} reports to {manager}")
                                        st.rerun()
                                else:
                                    st.warning("This relationship already exists.")
                            else:
                                st.error("Please select two different roles.")
                
                st.markdown("##### Current Reporting Structure")
                if not current_org_chart.get('edges'):
                    st.info("No reporting relationships defined yet.")
                else:
                    for i, edge in enumerate(list(current_org_chart['edges'])):
                        st.markdown(f"- **{edge['source']}** reports to **{edge['target']}**")
                        if st.button(f"Remove", key=f"remove_edge_{i}"):
                            current_org_chart['edges'].pop(i)
                            current_config['org_chart'] = current_org_chart
                            if save_config(current_config):
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

            # User Management Section
            st.subheader("Manage Users")
            with st.expander("View and Edit User Accounts", expanded=False):
                users_db = load_users()
                
                if not users_db:
                    st.info("No users in the system yet.")
                else:
                    st.markdown(f"**Total Users: {len(users_db)}**")
                    
                    # Create a searchable user list
                    user_emails = list(users_db.keys())
                    selected_user_email = st.selectbox(
                        "Select User to Edit:",
                        user_emails,
                        format_func=lambda email: f"{users_db[email].get('first_name', '')} {users_db[email].get('last_name', '')} ({email})",
                        key="user_edit_selector"
                    )
                    
                    if selected_user_email:
                        user = users_db[selected_user_email]
                        st.markdown(f"### Editing: {user.get('first_name', '')} {user.get('last_name', '')}")
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            new_first_name = st.text_input("First Name:", value=user.get('first_name', ''), key=f"edit_first_name_{selected_user_email}")
                            new_email = st.text_input("Email:", value=selected_user_email, key=f"edit_email_{selected_user_email}", disabled=True)
                            new_position = st.selectbox("Position/Role:", list(STAFF_ROLES.keys()), 
                                                       index=list(STAFF_ROLES.keys()).index(user.get('position')) if user.get('position') in STAFF_ROLES else 0,
                                                       key=f"edit_position_{selected_user_email}")
                        with col2:
                            new_last_name = st.text_input("Last Name:", value=user.get('last_name', ''), key=f"edit_last_name_{selected_user_email}")
                            new_is_admin = st.checkbox("Admin Privileges", value=user.get('is_admin', False), key=f"edit_is_admin_{selected_user_email}")
                        
                        col_a, col_b, col_c = st.columns([2, 2, 1])
                        with col_a:
                            if st.button("💾 Save Changes", key=f"save_user_changes_{selected_user_email}", type="primary"):
                                users_db[selected_user_email]['first_name'] = new_first_name
                                users_db[selected_user_email]['last_name'] = new_last_name
                                users_db[selected_user_email]['position'] = new_position
                                users_db[selected_user_email]['is_admin'] = new_is_admin
                                
                                if save_users(users_db):
                                    st.success(f"✅ User {new_first_name} {new_last_name} updated successfully!")
                                    st.rerun()
                                else:
                                    st.error("Failed to save user changes.")
                        
                        with col_b:
                            new_password = st.text_input("Reset Password (optional):", type="password", key=f"reset_password_{selected_user_email}")
                            if st.button("🔑 Reset Password", key=f"reset_pwd_btn_{selected_user_email}"):
                                if new_password:
                                    users_db[selected_user_email]['password_hash'] = hash_password(new_password)
                                    if save_users(users_db):
                                        st.success("✅ Password reset successfully!")
                                        st.rerun()
                                else:
                                    st.warning("Please enter a new password.")
                        
                        with col_c:
                            st.write("")
                            st.write("")
                            if st.button("🗑️ Delete User", key=f"delete_user_btn_{selected_user_email}"):
                                if selected_user_email != st.session_state.email:  # Prevent self-deletion
                                    del users_db[selected_user_email]
                                    if save_users(users_db):
                                        st.success(f"✅ User {selected_user_email} deleted.")
                                        st.rerun()
                                else:
                                    st.error("❌ You cannot delete your own account.")
                        
                        st.divider()
                        st.markdown("#### User Details")
                        st.json({
                            "Email": selected_user_email,
                            "Name": f"{user.get('first_name', '')} {user.get('last_name', '')}",
                            "Position": user.get('position', 'Unknown'),
                            "Admin": user.get('is_admin', False),
                            "Account Created": "N/A"  # Could add timestamp if tracked
                        })

    with results_tab:
        st.header("Results & Progress")
        st.write("Review past performance and track development.")

        results_data = load_results()

        def is_valid_score(value):
            score_str = str(value).strip()
            return score_str.isdigit() and 1 <= int(score_str) <= 4

        def parse_overall_score(text):
            if not text:
                return None

            import re
            rating_map = {
                "needs development": "1",
                "proficient": "3",
                "exemplary": "4"
            }

            explicit_match = re.search(r"^OVERALL_SCORE\s*:\s*([1-4])\b", text, flags=re.MULTILINE)
            if explicit_match:
                return explicit_match.group(1)

            for line in text.splitlines():
                cleaned = line.replace("**", "").strip()
                lower_line = cleaned.lower()

                if "overall" not in lower_line:
                    continue
                if "using the rubric" in lower_line or "provide" in lower_line:
                    continue

                if any(token in lower_line for token in ["overall score", "overall assessment", "overall rating"]):
                    match = re.search(r"overall\s+(?:score|assessment|rating)[^0-9]*([1-4])", lower_line)
                    if match:
                        return match.group(1)

                    for key, value in rating_map.items():
                        if key in lower_line:
                            return value

            overall_word_match = re.search(
                r"overall[^\n]{0,60}(needs development|proficient|exemplary)",
                text,
                flags=re.IGNORECASE
            )
            if overall_word_match:
                return rating_map.get(overall_word_match.group(1).lower())

            return None

        # Filter to show only completed results (hide pending reviews)
        completed_results = []
        for idx, res in enumerate(results_data):
            if res.get('status') != 'pending':
                res_with_index = dict(res)
                res_with_index["_result_index"] = idx
                completed_results.append(res_with_index)


        
        # Also include completed assigned scenarios
        assignments_data = load_assignments()
        users_db = load_users()
        for assignment in assignments_data.get("assignments", []):
            if assignment.get("completed") and assignment.get("reviewed"):
                # Get the staff email as unique identifier
                staff_email = assignment.get("staff_email", "")
                
                # Determine the role to display
                # Priority: Look up by email in users DB > assigned_role > staff_position > "Unknown Role"
                display_role = "Unknown Role"
                if staff_email and staff_email in users_db:
                    display_role = users_db[staff_email].get("position", "Unknown Role")
                else:
                    display_role = (
                        assignment.get("assigned_role") or 
                        assignment.get("staff_position") or 
                        "Unknown Role"
                    )
                
                # Get the staff name - handle both old and new format
                staff_name = assignment.get("staff_name", "Unknown Staff")
                
                # Try to get full name from users DB if available
                if staff_email and staff_email in users_db:
                    user_data = users_db[staff_email]
                    first = user_data.get("first_name", "")
                    last = user_data.get("last_name", "")
                    if first:
                        staff_name = f"{first} {last}".strip()
                
                # Fallback: try to get from email if name is missing
                if not staff_name or staff_name == "Staff Member":
                    staff_name = staff_email.split("@")[0].replace(".", " ").title() if "@" in staff_email else staff_email
                
                # Parse first and last name
                name_parts = staff_name.split()
                first_name = name_parts[0] if len(name_parts) > 0 else "Unknown"
                last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
                
                # Extract overall score from ai_analysis if available
                overall_score = assignment.get("overall_score", "N/A")
                ai_analysis = assignment.get("ai_analysis", "")
                if not is_valid_score(overall_score) and ai_analysis:
                    parsed_score = parse_overall_score(ai_analysis)
                    if parsed_score:
                        overall_score = parsed_score
                
                converted = {
                    "first_name": first_name,
                    "last_name": last_name,
                    "email": staff_email,
                    "role": display_role,
                    "difficulty": "Assigned Scenario",
                    "timestamp": assignment.get("response_date", assignment.get("assigned_date", "")),
                    "scenario": assignment.get("scenario", "N/A"),
                    "user_response": assignment.get("response", "N/A"),
                    "evaluation": assignment.get("ai_analysis", "N/A"),
                    "overall_score": overall_score,
                    "status": "completed",
                    "is_assigned": True,
                    "assignment_id": assignment.get("id"),
                    "supervisor_notes": assignment.get("supervisor_feedback", ""),
                    "supervisor_feedback": assignment.get("supervisor_feedback", ""),
                    "reviewed_by": assignment.get("reviewed_by", ""),
                    "review_date": assignment.get("review_date", "")
                }
                completed_results.append(converted)

        if st.session_state.get('is_admin'):
            with st.expander("Admin Tools"):
                if st.button("Retro-fix stored analysis scores", key="retro_fix_scores"):
                    updated_results = 0
                    for res in results_data:
                        evaluation_text = res.get("evaluation", "")
                        parsed_score = parse_overall_score(evaluation_text)
                        if parsed_score and (not is_valid_score(res.get("overall_score")) or res.get("overall_score") != parsed_score):
                            res["overall_score"] = parsed_score
                            updated_results += 1

                    assignments_data = load_assignments()
                    updated_assignments = 0
                    for assignment in assignments_data.get("assignments", []):
                        analysis_text = assignment.get("ai_analysis", "")
                        parsed_score = parse_overall_score(analysis_text)
                        if parsed_score and (not is_valid_score(assignment.get("overall_score")) or assignment.get("overall_score") != parsed_score):
                            assignment["overall_score"] = parsed_score
                            updated_assignments += 1

                    save_results(results_data)
                    save_assignments(assignments_data)
                    st.success(f"Updated scores in results: {updated_results}, assignments: {updated_assignments}.")
                    st.rerun()

                # Rerun selected analyses via AI
                def build_evaluation_prompt(role, scenario, response):
                    return f"""
You are evaluating a staff response using the Guiding NORTH rubric.

Role: {role}
Scenario: {scenario}
User Response: {response}

Provide the evaluation using the strict format below.

### Guiding NORTH Evaluation:

OVERALL_SCORE: [Your 1-4 Rating]

**Overall Score:** [Your 1-4 Rating]

---

**N - Navigate Needs:**
- **Rating:** [Needs Development | Proficient | Exemplary]
- **Justification:** [Your Justification]

**O - Own the Outcome:**
- **Rating:** [Needs Development | Proficient | Exemplary]
- **Justification:** [Your Justification]

**R - Respond Respectfully:**
- **Rating:** [Needs Development | Proficient | Exemplary]
- **Justification:** [Your Justification]

**T - Timely & Truthful:**
- **Rating:** [Needs Development | Proficient | Exemplary]
- **Justification:** [Your Justification]

**H - Help Proactively:**
- **Rating:** [Needs Development | Proficient | Exemplary]
- **Justification:** [Your Justification]
"""

                rerun_options = []
                rerun_labels = {}
                for res in completed_results:
                    if res.get("is_assigned") and res.get("assignment_id"):
                        option_id = f"assignment:{res.get('assignment_id')}"
                    else:
                        option_id = f"result:{res.get('_result_index', 'na')}"

                    name = f"{res.get('first_name', '')} {res.get('last_name', '')}".strip() or res.get("user_name", "Unknown")
                    label = f"{option_id} | {res.get('timestamp', 'N/A')[:16]} | {name} | {res.get('role', 'N/A')}"
                    rerun_options.append(option_id)
                    rerun_labels[option_id] = label

                selected_to_rerun = st.multiselect(
                    "Select analyses to rerun",
                    options=rerun_options,
                    format_func=lambda x: rerun_labels.get(x, x),
                    key="rerun_analysis_select"
                )

                if st.button("Rerun Selected Analyses", key="rerun_selected_analyses"):
                    client = st.session_state.get('genai_client')
                    if not client:
                        st.error("No API client available. Please enter an API key and login.")
                    elif not selected_to_rerun:
                        st.warning("Select at least one analysis to rerun.")
                    else:
                        updated_results = 0
                        updated_assignments = 0
                        skipped = 0
                        errors = 0

                        assignments_data_updated = load_assignments()
                        for option_id in selected_to_rerun:
                            if option_id.startswith("assignment:"):
                                assignment_id = option_id.split(":", 1)[1]
                                assignment = next(
                                    (a for a in assignments_data_updated.get("assignments", []) if str(a.get("id")) == assignment_id),
                                    None
                                )
                                if not assignment:
                                    skipped += 1
                                    continue

                                role = assignment.get("assigned_role") or assignment.get("staff_position") or "Unknown Role"
                                scenario = assignment.get("scenario", "")
                                response = assignment.get("response", "")
                                if not scenario or not response:
                                    skipped += 1
                                    continue

                                try:
                                    prompt = build_evaluation_prompt(role, scenario, response)
                                    ai_response = client.models.generate_content(
                                        model=st.session_state.get("selected_model", "models/gemini-1.5-flash"),
                                        contents=prompt
                                    )
                                    analysis_text = ai_response.text if ai_response.text else "Unable to analyze response"
                                    assignment["ai_analysis"] = analysis_text
                                    parsed_score = parse_overall_score(analysis_text)
                                    if parsed_score:
                                        assignment["overall_score"] = parsed_score
                                    updated_assignments += 1
                                except Exception:
                                    errors += 1
                            else:
                                result_index = option_id.split(":", 1)[1]
                                if not result_index.isdigit():
                                    skipped += 1
                                    continue

                                result_index = int(result_index)
                                if result_index < 0 or result_index >= len(results_data):
                                    skipped += 1
                                    continue

                                res = results_data[result_index]
                                scenario = res.get("scenario", "")
                                response = res.get("user_response", "")
                                role = res.get("role", "Unknown Role")
                                if not scenario or not response:
                                    skipped += 1
                                    continue

                                try:
                                    prompt = build_evaluation_prompt(role, scenario, response)
                                    ai_response = client.models.generate_content(
                                        model=st.session_state.get("selected_model", "models/gemini-1.5-flash"),
                                        contents=prompt
                                    )
                                    analysis_text = ai_response.text if ai_response.text else "Unable to analyze response"
                                    res["evaluation"] = analysis_text
                                    parsed_score = parse_overall_score(analysis_text)
                                    if parsed_score:
                                        res["overall_score"] = parsed_score
                                    updated_results += 1
                                except Exception:
                                    errors += 1

                        save_results(results_data)
                        save_assignments(assignments_data_updated)
                        st.success(
                            f"Rerun complete. Updated results: {updated_results}, assignments: {updated_assignments}, skipped: {skipped}, errors: {errors}."
                        )
                        st.rerun()

        if not completed_results:
            st.info("No completed results yet.")
        else:
            # Filter results based on user role and access permissions
            if st.session_state.get('is_admin'):
                # Admin sees: ALL completed scores
                filtered_results = completed_results
                st.info(f"📊 Admin view: Viewing all completed results from all users ({len(completed_results)} total).")
            elif st.session_state.get('user_role') == 'supervisor':
                # Supervisor sees: their own scores + all direct reports' scores (completed only)
                allowed_emails = [st.session_state.email] + [
                    res.get('email') for res in completed_results 
                    if res.get('role') in st.session_state.direct_reports
                ]
                filtered_results = [res for res in completed_results if res.get('email') in allowed_emails]
                st.info(f"📊 You are viewing your results and your {len(st.session_state.direct_reports)} direct report role(s).")
            else:
                # Staff sees: only their own completed scores
                filtered_results = [res for res in completed_results if res.get('email') == st.session_state.email]
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
                                st.metric(label="Your Average Score", value=f"{avg_score:.2f} / 4")
                            else:
                                st.metric(label="Your Average Score", value="N/A")
                        
                        with col2:
                            if not is_group_view:
                                # Show comparison to role group (individual avg - group avg)
                                user_avg = sum(scores) / len(scores) if scores else 0
                                comparison = user_avg - role_group_avg
                                st.metric(label="vs Role Group Average", value=f"{role_group_avg:.2f} / 4",
                                        delta=f"{comparison:+.2f}" if comparison != 0 else "Same",
                                        delta_color="normal")
                            else:
                                st.metric(label=f"{role_name} Group Average", value=f"{role_group_avg:.2f} / 4")
                        
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
                                yaxis_title="Score (out of 4)",
                                hovermode='x unified',
                                height=400,
                                yaxis=dict(range=[0, 4])
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
                                        value=f"{avg:.2f} / 4",
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
                                yaxis=dict(range=[0, 4])
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
                                st.markdown(f"**Submitted:** {result.get('timestamp', 'N/A')}")

                                if st.session_state.get('is_admin'):
                                    st.markdown("---")
                                    delete_key = (
                                        f"delete_result_{role_name}_"
                                        f"{i}_"
                                        f"{result.get('_result_index', 'na')}_"
                                        f"{result.get('assignment_id', 'na')}_"
                                        f"{result.get('timestamp', 'na')}_"
                                        f"{result.get('email', 'na')}"
                                    )
                                    if st.button("Delete Result", key=delete_key):
                                        if result.get("is_assigned") and result.get("assignment_id"):
                                            assignments_data_updated = load_assignments()
                                            assignments_data_updated["assignments"] = [
                                                a for a in assignments_data_updated.get("assignments", [])
                                                if a.get("id") != result.get("assignment_id")
                                            ]
                                            save_assignments(assignments_data_updated)
                                        else:
                                            results_data_updated = load_results()
                                            result_index = result.get("_result_index")
                                            if isinstance(result_index, int) and 0 <= result_index < len(results_data_updated):
                                                results_data_updated.pop(result_index)
                                            else:
                                                results_data_updated = [
                                                    r for r in results_data_updated
                                                    if not (
                                                        r.get("email") == result.get("email") and
                                                        r.get("timestamp") == result.get("timestamp") and
                                                        r.get("scenario") == result.get("scenario")
                                                    )
                                                ]
                                            save_results(results_data_updated)

                                        st.success("Result deleted.")
                                        st.rerun()
                                
                                # Display supervisor review information if available
                                if result.get('reviewed_by'):
                                    st.markdown("---")
                                    st.markdown("#### Supervisor Review")
                                    review_date = result.get('review_date', 'N/A')
                                    if review_date and review_date != 'N/A':
                                        # Format the ISO timestamp for readability
                                        try:
                                            from datetime import datetime as dt
                                            review_dt = dt.fromisoformat(review_date)
                                            formatted_review_date = review_dt.strftime("%B %d, %Y at %I:%M %p")
                                        except:
                                            formatted_review_date = review_date
                                    else:
                                        formatted_review_date = review_date
                                    
                                    st.success(f"✅ Reviewed by: **{result.get('reviewed_by')}**")
                                    st.success(f"📅 Review Date: **{formatted_review_date}**")
                                    
                                    if result.get('supervisor_notes'):
                                        st.markdown("**Supervisor Notes:**")
                                        st.info(result.get('supervisor_notes'))
                                
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
