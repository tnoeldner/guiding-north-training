import streamlit as st
import google.genai as genai
from google.genai import types
import json
import random
import io
import os
import re
import secrets
import hashlib
import numpy as np
from PyPDF2 import PdfReader
from streamlit_agraph import agraph, Node, Edge, Config
from datetime import datetime
import plotly.graph_objects as go
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
import psycopg2
from psycopg2 import pool
st.set_page_config(
    page_title="Guiding NORTH: HRL Training",
    page_icon="🧭",
    layout="wide",
)

# --- Database Configuration ---
@st.cache_resource
def get_db_pool():
    """Creates a PostgreSQL connection pool."""
    try:
        return psycopg2.pool.SimpleConnectionPool(
            1, 10, dsn=st.secrets["NEON_DB_CONNECTION_STRING"]
        )
    except Exception as e:
        st.error(f"Error creating database connection pool: {e}")
        return None

def init_db():
    """Initialize the database and create tables if they don't exist."""
    db_pool = get_db_pool()
    if not db_pool:
        st.error("Database connection pool is not available.")
        return

    conn = None
    try:
        conn = db_pool.getconn()
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    email VARCHAR(255) PRIMARY KEY,
                    password_hash VARCHAR(255) NOT NULL,
                    is_admin BOOLEAN DEFAULT FALSE,
                    first_name VARCHAR(100),
                    last_name VARCHAR(100),
                    position VARCHAR(100),
                    created_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS results (
                    id SERIAL PRIMARY KEY,
                    first_name VARCHAR(100),
                    last_name VARCHAR(100),
                    email VARCHAR(255),
                    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    role VARCHAR(100),
                    difficulty VARCHAR(50),
                    scenario TEXT,
                    user_response TEXT,
                    evaluation TEXT,
                    overall_score VARCHAR(50),
                    status VARCHAR(50) DEFAULT 'pending',
                    reviewed_by VARCHAR(255),
                    review_date TIMESTAMP WITH TIME ZONE,
                    supervisor_notes TEXT
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS scenario_assignments (
                    id SERIAL PRIMARY KEY,
                    email VARCHAR(255) NOT NULL,
                    scenario_name VARCHAR(255) NOT NULL,
                    status VARCHAR(50) DEFAULT 'assigned',
                    assigned_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    completed_date TIMESTAMP WITH TIME ZONE
                );
            """)
            # Migrate: add rich columns if they don't exist yet
            cur.execute("""
                ALTER TABLE scenario_assignments
                    ADD COLUMN IF NOT EXISTS supervisor_email VARCHAR(255),
                    ADD COLUMN IF NOT EXISTS supervisor_name VARCHAR(255),
                    ADD COLUMN IF NOT EXISTS staff_name VARCHAR(255),
                    ADD COLUMN IF NOT EXISTS assigned_role VARCHAR(255),
                    ADD COLUMN IF NOT EXISTS scenario_text TEXT,
                    ADD COLUMN IF NOT EXISTS response TEXT,
                    ADD COLUMN IF NOT EXISTS response_date TIMESTAMP WITH TIME ZONE,
                    ADD COLUMN IF NOT EXISTS ai_analysis TEXT,
                    ADD COLUMN IF NOT EXISTS supervisor_feedback TEXT,
                    ADD COLUMN IF NOT EXISTS reviewed_date TIMESTAMP WITH TIME ZONE,
                    ADD COLUMN IF NOT EXISTS difficulty VARCHAR(50),
                    ADD COLUMN IF NOT EXISTS token VARCHAR(64),
                    ADD COLUMN IF NOT EXISTS token_used BOOLEAN DEFAULT FALSE;
            """)
            cur.execute("""
                ALTER TABLE results
                    ADD COLUMN IF NOT EXISTS exemplary_response TEXT,
                    ADD COLUMN IF NOT EXISTS exemplary_feedback TEXT,
                    ADD COLUMN IF NOT EXISTS exemplary_refined TEXT;
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sop_chunks (
                    id SERIAL PRIMARY KEY,
                    doc_name VARCHAR(255) NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    heading VARCHAR(500),
                    content TEXT NOT NULL,
                    tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
                );
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS sop_chunks_tsv_idx ON sop_chunks USING GIN(tsv);
            """)
            conn.commit()
    except Exception as e:
        st.error(f"Database initialization failed: {e}")
    finally:
        if conn:
            db_pool.putconn(conn)

init_db()

# --- File Path Constants ---
FRAMEWORK_FILE = "guiding_north_framework.md"
KNOWLEDGE_BASE_FILE = "HRLKnowledgeBase"
WEBSITE_KB_FILE = "und_housing_website.md"
BEST_PRACTICES_FILE = "housing_best_practices.md"
CONFIG_FILE = "config.json"

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
    """Loads all users from the database."""
    db_pool = get_db_pool()
    if not db_pool:
        st.error("Database connection is not available.")
        return {}
    conn = None
    try:
        conn = db_pool.getconn()
        with conn.cursor() as cur:
            cur.execute("SELECT email, password_hash, is_admin, first_name, last_name, position FROM users")
            users = {}
            for record in cur.fetchall():
                email, pw_hash, is_admin, first, last, pos = record
                users[email] = {
                    "password_hash": pw_hash,
                    "is_admin": is_admin,
                    "first_name": first,
                    "last_name": last,
                    "position": pos
                }
            return users
    except Exception as e:
        st.error(f"Error loading users from database: {e}")
        return {}
    finally:
        if conn:
            db_pool.putconn(conn)

def save_user(email, password, is_admin=False, first_name="", last_name="", position=""):
    """Saves or updates a single user in the database."""
    db_pool = get_db_pool()
    if not db_pool:
        st.error("Database connection is not available.")
        return
    conn = None
    password_hash = generate_password_hash(password)
    try:
        conn = db_pool.getconn()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (email, password_hash, is_admin, first_name, last_name, position)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (email) DO UPDATE SET
                    password_hash = EXCLUDED.password_hash,
                    is_admin = EXCLUDED.is_admin,
                    first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name,
                    position = EXCLUDED.position;
                """,
                (email, password_hash, is_admin, first_name, last_name, position)
            )
            conn.commit()
    except Exception as e:
        st.error(f"Error saving user to database: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            db_pool.putconn(conn)

def delete_user(email):
    """Deletes a user from the database."""
    db_pool = get_db_pool()
    if not db_pool:
        st.error("Database connection is not available.")
        return False
    conn = None
    try:
        conn = db_pool.getconn()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE email = %s", (email,))
            conn.commit()
            return True
    except Exception as e:
        st.error(f"Error deleting user from database: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            db_pool.putconn(conn)

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

def extract_exemplary_response(evaluation_text):
    """Extracts the Exemplary Response / Call Example section from an AI evaluation."""
    if not evaluation_text:
        return None
    import re
    # Match from the exemplary header to end of string — covers both scenario and call analysis headings
    patterns = [
        r"(?:Exemplary Call Example|Exemplary Response Example|Exemplary Response|Exemplary Answer)[:\s*#]*\n(.*)",
        r"\*\*Exemplary (?:Call Example|Response(?:[^*]*)?)\*\*[:\s]*\n(.*)",
        r"#{1,4}\s*Exemplary (?:Call Example|Response)[:\s]*\n(.*)",
    ]
    for pattern in patterns:
        m = re.search(pattern, evaluation_text, re.IGNORECASE | re.DOTALL)
        if m:
            return m.group(1).strip()
    return None

def load_results():
    """Loads all results from the database."""
    db_pool = get_db_pool()
    if not db_pool:
        return []
    conn = None
    try:
        conn = db_pool.getconn()
        with conn.cursor() as cur:
            cur.execute("SELECT id, first_name, last_name, email, timestamp, role, difficulty, scenario, user_response, evaluation, overall_score, status, reviewed_by, review_date, supervisor_notes, exemplary_response, exemplary_feedback, exemplary_refined FROM results ORDER BY timestamp DESC")
            results = []
            for record in cur.fetchall():
                results.append({
                    "id": record[0],
                    "first_name": record[1],
                    "last_name": record[2],
                    "email": record[3],
                    "timestamp": record[4].isoformat(),
                    "role": record[5],
                    "difficulty": record[6],
                    "scenario": record[7],
                    "user_response": record[8],
                    "evaluation": record[9],
                    "overall_score": record[10],
                    "status": record[11],
                    "reviewed_by": record[12],
                    "review_date": record[13].isoformat() if record[13] else None,
                    "supervisor_notes": record[14],
                    "exemplary_response": record[15],
                    "exemplary_feedback": record[16],
                    "exemplary_refined": record[17],
                })
            return results
    except Exception as e:
        st.error(f"Error loading results from database: {e}")
        return []
    finally:
        if conn:
            db_pool.putconn(conn)

def save_results(data):
    """Saves a single result dict to the database."""
    db_pool = get_db_pool()
    if not db_pool:
        return False
    conn = None
    try:
        conn = db_pool.getconn()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO results (first_name, last_name, email, timestamp, role, difficulty, scenario, user_response, evaluation, overall_score, exemplary_response)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """,
                (
                    data.get("first_name"), data.get("last_name"), data.get("email"),
                    data.get("timestamp"), data.get("role"), data.get("difficulty"),
                    data.get("scenario"), data.get("user_response"),
                    data.get("evaluation"), data.get("overall_score"),
                    data.get("exemplary_response")
                )
            )
            conn.commit()
            return True
    except Exception as e:
        st.error(f"Error saving result to database: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            db_pool.putconn(conn)

def update_result(result_id, **fields):
    """Updates specific fields of an existing result row by id."""
    db_pool = get_db_pool()
    if not db_pool or not fields:
        return False
    allowed = {"evaluation", "overall_score", "status", "reviewed_by", "review_date", "supervisor_notes",
               "exemplary_response", "exemplary_feedback", "exemplary_refined"}
    safe_fields = {k: v for k, v in fields.items() if k in allowed}
    if not safe_fields:
        return False
    conn = None
    try:
        conn = db_pool.getconn()
        with conn.cursor() as cur:
            # Coerce review_date to a datetime object if it's a string
            if "review_date" in safe_fields and isinstance(safe_fields["review_date"], str):
                try:
                    safe_fields["review_date"] = datetime.fromisoformat(safe_fields["review_date"])
                except ValueError:
                    safe_fields["review_date"] = None
            set_clause = ", ".join(f"{k} = %s" for k in safe_fields)
            values = list(safe_fields.values()) + [result_id]
            cur.execute(f"UPDATE results SET {set_clause} WHERE id = %s", values)
            conn.commit()
            return True
    except Exception as e:
        st.error(f"Error updating result: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            db_pool.putconn(conn)

def delete_result(result_id):
    """Deletes a result row by id."""
    db_pool = get_db_pool()
    if not db_pool:
        return False
    conn = None
    try:
        conn = db_pool.getconn()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM results WHERE id = %s", (result_id,))
            conn.commit()
            return True
    except Exception as e:
        st.error(f"Error deleting result: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            db_pool.putconn(conn)

def chunk_text(text, chunk_size=500, overlap=50):
    """Split text into overlapping word-based chunks."""
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = words[i:i + chunk_size]
        chunks.append(" ".join(chunk))
        if i + chunk_size >= len(words):
            break
        i += chunk_size - overlap
    return chunks

def store_sop_chunks(doc_name, chunks, headings=None):
    """Delete existing doc then insert new chunks. headings is optional list matching chunks."""
    db_pool = get_db_pool()
    conn = None
    try:
        conn = db_pool.getconn()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sop_chunks WHERE doc_name = %s", (doc_name,))
            for idx, content in enumerate(chunks):
                heading = (headings[idx] if headings and idx < len(headings) else None)
                cur.execute(
                    "INSERT INTO sop_chunks (doc_name, chunk_index, heading, content) VALUES (%s, %s, %s, %s)",
                    (doc_name, idx, heading, content)
                )
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error storing SOP chunks: {e}")
        return False
    finally:
        if conn:
            db_pool.putconn(conn)

def search_sop_chunks(query_text, limit=5):
    """Full-text search returning list of (doc_name, chunk_index, content) tuples."""
    if not query_text or not query_text.strip():
        return []
    db_pool = get_db_pool()
    conn = None
    try:
        conn = db_pool.getconn()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT doc_name, chunk_index, content FROM sop_chunks
                WHERE tsv @@ plainto_tsquery('english', %s)
                ORDER BY ts_rank(tsv, plainto_tsquery('english', %s)) DESC
                LIMIT %s
            """, (query_text, query_text, limit))
            return cur.fetchall()
    except Exception:
        return []
    finally:
        if conn:
            db_pool.putconn(conn)

def list_sop_documents():
    """Return list of dicts with doc_name, chunk_count, uploaded_at."""
    db_pool = get_db_pool()
    conn = None
    try:
        conn = db_pool.getconn()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT doc_name, COUNT(*) AS chunk_count, MIN(id) AS first_id
                FROM sop_chunks
                GROUP BY doc_name
                ORDER BY first_id ASC
            """)
            rows = cur.fetchall()
            return [{"doc_name": r[0], "chunk_count": r[1]} for r in rows]
    except Exception:
        return []
    finally:
        if conn:
            db_pool.putconn(conn)

def delete_sop_document(doc_name):
    db_pool = get_db_pool()
    conn = None
    try:
        conn = db_pool.getconn()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sop_chunks WHERE doc_name = %s", (doc_name,))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error deleting SOP document: {e}")
        return False
    finally:
        if conn:
            db_pool.putconn(conn)

def get_sop_chunks_for_doc(doc_name):
    """Return all chunks for a specific document ordered by chunk_index."""
    db_pool = get_db_pool()
    conn = None
    try:
        conn = db_pool.getconn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT chunk_index, content FROM sop_chunks WHERE doc_name = %s ORDER BY chunk_index ASC",
                (doc_name,)
            )
            return cur.fetchall()
    except Exception:
        return []
    finally:
        if conn:
            db_pool.putconn(conn)

def retrieve_sop_context(query_text):
    """Return a formatted block of relevant SOP chunks for prompt injection."""
    results = search_sop_chunks(query_text, limit=5)
    if not results:
        return ""
    parts = [content for doc_name, chunk_index, content in results]
    joined = "\n\n---\n\n".join(parts)
    return (
        f"\n\n===RELEVANT SOP PROCEDURES===\n"
        f"(Each SOP section below contains its own Document ID in the format HRL-XXX-XX. "
        f"When referencing any of this SOP content in your evaluation, cite the Document ID "
        f"that appears within that section at the end of the relevant sentence, "
        f"formatted as: (SOP Document ID: HRL-XXX-XX))\n\n"
        f"{joined}\n===END SOP PROCEDURES===\n"
    )

def load_exemplary_examples(limit=5):
    """Loads supervisor-refined exemplary responses for few-shot prompting."""
    db_pool = get_db_pool()
    if not db_pool:
        return []
    conn = None
    try:
        conn = db_pool.getconn()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT scenario, exemplary_response, exemplary_feedback, exemplary_refined,
                       reviewed_by, review_date
                FROM results
                WHERE exemplary_refined IS NOT NULL AND exemplary_refined != ''
                ORDER BY review_date DESC NULLS LAST
                LIMIT %s
            """, (limit,))
            rows = cur.fetchall()
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in rows]
    except Exception:
        return []
    finally:
        if conn:
            db_pool.putconn(conn)


def sync_corrections_to_knowledge_base():
    """Writes all supervisor-approved exemplary standards into the HRLKnowledgeBase file."""
    examples = load_exemplary_examples(limit=100)
    START_MARKER = "===BEGIN_SUPERVISOR_EXEMPLARY_STANDARDS==="
    END_MARKER = "===END_SUPERVISOR_EXEMPLARY_STANDARDS==="
    try:
        with open(KNOWLEDGE_BASE_FILE, 'r', encoding='utf-8', errors='replace') as f:
            current_content = f.read()
    except FileNotFoundError:
        current_content = ""
    # Strip existing auto-generated section
    start_idx = current_content.find(START_MARKER)
    if start_idx != -1:
        end_idx = current_content.find(END_MARKER)
        if end_idx != -1:
            current_content = current_content[:start_idx].rstrip()
        else:
            current_content = current_content[:start_idx].rstrip()
    if not examples:
        with open(KNOWLEDGE_BASE_FILE, 'w', encoding='utf-8') as f:
            f.write(current_content)
        return
    lines = [
        "",
        "",
        START_MARKER,
        "## Supervisor-Approved Exemplary Standards",
        "Source: Auto-generated from supervisor-reviewed training corrections.",
        "Context: The following standards represent supervisor-approved expectations for exemplary staff performance.",
        "        The AI must use these as authoritative benchmarks when writing any exemplary response.",
        ""
    ]
    for i, ex in enumerate(examples, 1):
        review_date = str(ex.get('review_date', ''))[:10]
        reviewer = ex.get('reviewed_by', 'supervisor')
        lines.append(f"Standard {i} (reviewed {review_date} by {reviewer}):")
        if ex.get('scenario'):
            preview = ex['scenario'][:400] + ("..." if len(ex.get('scenario', '')) > 400 else "")
            lines.append(f"  Scenario Context: {preview}")
        if ex.get('exemplary_feedback'):
            lines.append(f"  Supervisor Corrections Applied: {ex['exemplary_feedback']}")
        lines.append(f"  Approved Exemplary Response:")
        lines.append(f"  {ex.get('exemplary_refined', 'N/A')}")
        lines.append("")
    lines.append(END_MARKER)
    new_content = current_content + "\n".join(lines)
    with open(KNOWLEDGE_BASE_FILE, 'w', encoding='utf-8') as f:
        f.write(new_content)


def load_config():
    """Loads the configuration from the database, migrating from config.json on first run."""
    db_pool = get_db_pool()
    if not db_pool:
        st.error("Database connection is not available for loading config.")
        return {"staff_roles": {}, "org_chart": {'nodes': [], 'edges': []}}
    conn = None
    try:
        conn = db_pool.getconn()
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM app_config WHERE key = 'default_config'")
            record = cur.fetchone()
            if record and record[0]:
                return record[0]
            else:
                # No config in DB — attempt to migrate from config.json
                try:
                    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                        config_data = json.load(f)
                    if 'org_chart' not in config_data:
                        config_data['org_chart'] = {'nodes': [], 'edges': []}
                    # Seed the database so future loads come from there
                    cur.execute(
                        """
                        INSERT INTO app_config (key, value)
                        VALUES ('default_config', %s)
                        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
                        """,
                        (json.dumps(config_data),)
                    )
                    conn.commit()
                    return config_data
                except (FileNotFoundError, json.JSONDecodeError):
                    return {"staff_roles": {}, "org_chart": {'nodes': [], 'edges': []}}
    except Exception as e:
        st.error(f"Error loading configuration from database: {e}")
        return {"staff_roles": {}, "org_chart": {'nodes': [], 'edges': []}}
    finally:
        if conn:
            db_pool.putconn(conn)

def save_config(config_data):
    """Saves the configuration to the database."""
    db_pool = get_db_pool()
    if not db_pool:
        st.error("Database connection is not available for saving config.")
        return False
    conn = None
    try:
        conn = db_pool.getconn()
        with conn.cursor() as cur:
            # Use JSONB for the value and an ON CONFLICT clause to handle updates
            cur.execute(
                """
                INSERT INTO app_config (key, value)
                VALUES ('default_config', %s)
                ON CONFLICT (key) DO UPDATE SET
                    value = EXCLUDED.value;
                """,
                (json.dumps(config_data),)
            )
            conn.commit()
        return True
    except Exception as e:
        st.error(f"Failed to save configuration to database: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            db_pool.putconn(conn)

def load_assignments():
    """Loads all scenario assignments from the database."""
    db_pool = get_db_pool()
    if not db_pool:
        return []
    conn = None
    try:
        conn = db_pool.getconn()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, email, scenario_name, status, assigned_date, completed_date,
                       supervisor_email, supervisor_name, staff_name, assigned_role,
                       scenario_text, response, response_date, ai_analysis,
                       supervisor_feedback, reviewed_date, difficulty
                FROM scenario_assignments
            """)
            assignments = []
            for r in cur.fetchall():
                assignments.append({
                    "id": r[0],
                    "email": r[1],
                    "staff_email": r[1],        # alias for legacy references
                    "scenario_name": r[2],
                    "topic": r[2],              # alias for legacy references
                    "status": r[3],
                    "assigned_date": r[4].isoformat() if r[4] else None,
                    "completed_date": r[5].isoformat() if r[5] else None,
                    "supervisor_email": r[6],
                    "supervisor_name": r[7],
                    "staff_name": r[8],
                    "assigned_role": r[9],
                    "scenario_text": r[10],
                    "scenario": r[10],          # alias for legacy references
                    "response": r[11],
                    "response_date": r[12].isoformat() if r[12] else None,
                    "ai_analysis": r[13],
                    "supervisor_feedback": r[14],
                    "reviewed_date": r[15].isoformat() if r[15] else None,
                    "difficulty": r[16],
                })
            return assignments
    except Exception as e:
        st.error(f"Error loading assignments from database: {e}")
        return []
    finally:
        if conn:
            db_pool.putconn(conn)

def get_assignment_by_token(token):
    """Looks up an assignment by its magic-link token. Returns the assignment dict or None."""
    db_pool = get_db_pool()
    if not db_pool or not token:
        return None
    conn = None
    try:
        conn = db_pool.getconn()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, email, scenario_name, status, assigned_date,
                       supervisor_email, supervisor_name, staff_name, assigned_role,
                       scenario_text, response, ai_analysis, difficulty, token_used
                FROM scenario_assignments
                WHERE token = %s
            """, (token,))
            row = cur.fetchone()
            if not row:
                return None
            return {
                "id": row[0], "email": row[1], "scenario_name": row[2],
                "topic": row[2], "status": row[3],
                "assigned_date": row[4].isoformat() if row[4] else None,
                "supervisor_email": row[5], "supervisor_name": row[6],
                "staff_name": row[7], "assigned_role": row[8],
                "scenario": row[9], "scenario_text": row[9],
                "response": row[10], "ai_analysis": row[11],
                "difficulty": row[12], "token_used": row[13],
            }
    except Exception:
        return None
    finally:
        if conn:
            db_pool.putconn(conn)


def mark_token_used(assignment_id):
    """Marks the magic-link token for an assignment as used so it cannot be resubmitted."""
    db_pool = get_db_pool()
    if not db_pool:
        return
    conn = None
    try:
        conn = db_pool.getconn()
        with conn.cursor() as cur:
            cur.execute("UPDATE scenario_assignments SET token_used = TRUE WHERE id = %s", (assignment_id,))
            conn.commit()
    except Exception:
        pass
    finally:
        if conn:
            db_pool.putconn(conn)


def save_assignment(email, scenario_name, supervisor_email=None, supervisor_name=None,
                    staff_name=None, assigned_role=None, scenario_text=None, difficulty=None):
    """Saves a new scenario assignment to the database. Returns the token string, or None on failure."""
    db_pool = get_db_pool()
    if not db_pool:
        return None
    conn = None
    assignment_token = uuid.uuid4().hex
    try:
        conn = db_pool.getconn()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO scenario_assignments
                    (email, scenario_name, supervisor_email, supervisor_name,
                     staff_name, assigned_role, scenario_text, difficulty, token)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (email, scenario_name, supervisor_email, supervisor_name,
                 staff_name, assigned_role, scenario_text, difficulty, assignment_token)
            )
            conn.commit()
            return assignment_token
    except Exception as e:
        st.error(f"Error saving assignment to database: {e}")
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            db_pool.putconn(conn)

def update_assignment_status(assignment_id, status, supervisor_feedback=None):
    """Updates the status of a scenario assignment, optionally saving supervisor feedback."""
    db_pool = get_db_pool()
    if not db_pool:
        return False
    conn = None
    try:
        conn = db_pool.getconn()
        with conn.cursor() as cur:
            if supervisor_feedback is not None:
                reviewed_date = datetime.now() if status == "reviewed" else None
                cur.execute(
                    """UPDATE scenario_assignments
                       SET status = %s, supervisor_feedback = %s, reviewed_date = %s
                       WHERE id = %s""",
                    (status, supervisor_feedback, reviewed_date, assignment_id)
                )
            else:
                completed_date = datetime.now() if status == "completed" else None
                cur.execute(
                    "UPDATE scenario_assignments SET status = %s, completed_date = %s WHERE id = %s",
                    (status, completed_date, assignment_id)
                )
            conn.commit()
            return True
    except Exception as e:
        st.error(f"Error updating assignment status: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            db_pool.putconn(conn)

def save_assignment_response(assignment_id, response, ai_analysis=None):
    """Saves a staff member's response and AI analysis for an assigned scenario."""
    db_pool = get_db_pool()
    if not db_pool:
        return False
    conn = None
    try:
        conn = db_pool.getconn()
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE scenario_assignments
                   SET response = %s, ai_analysis = %s, response_date = %s, status = 'completed'
                   WHERE id = %s""",
                (response, ai_analysis, datetime.now(), assignment_id)
            )
            conn.commit()
            return True
    except Exception as e:
        st.error(f"Error saving assignment response: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            db_pool.putconn(conn)

def delete_assignment(assignment_id):
    """Deletes a scenario assignment from the database."""
    db_pool = get_db_pool()
    if not db_pool:
        return False
    conn = None
    try:
        conn = db_pool.getconn()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM scenario_assignments WHERE id = %s", (assignment_id,))
            conn.commit()
            return True
    except Exception as e:
        st.error(f"Error deleting assignment: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            db_pool.putconn(conn)

def save_users(users_dict):
    """Compatibility adapter — upserts all users in the dict to the database."""
    db_pool = get_db_pool()
    if not db_pool:
        return False
    conn = None
    try:
        conn = db_pool.getconn()
        with conn.cursor() as cur:
            for email, user_data in users_dict.items():
                cur.execute(
                    """
                    INSERT INTO users (email, password_hash, is_admin, first_name, last_name, position)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (email) DO UPDATE SET
                        password_hash = EXCLUDED.password_hash,
                        is_admin = EXCLUDED.is_admin,
                        first_name = EXCLUDED.first_name,
                        last_name = EXCLUDED.last_name,
                        position = EXCLUDED.position;
                    """,
                    (
                        email,
                        user_data.get('password_hash'),
                        user_data.get('is_admin', False),
                        user_data.get('first_name', ''),
                        user_data.get('last_name', ''),
                        user_data.get('position', '')
                    )
                )
            conn.commit()
        return True
    except Exception as e:
        st.error(f"Error saving users: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            db_pool.putconn(conn)

def save_assignments(assignments_data):
    """Compatibility stub — assignments are managed individually via DB functions."""
    # In the DB model, assignments are saved/updated one at a time.
    # This stub exists for legacy call-sites and returns True to avoid crashes.
    return True

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


# ─────────────────────────────────────────────────────────────────────────────
# Magic-link token page — renders standalone, no login required
# ─────────────────────────────────────────────────────────────────────────────
# Read token param — handle both Streamlit ≥1.30 (st.query_params dict-style)
# and older versions (st.experimental_get_query_params returns lists)
try:
    _token_param = st.query_params.get("token") or ""
except Exception:
    try:
        _token_param = st.experimental_get_query_params().get("token", [""])[0] or ""  # noqa
    except Exception:
        _token_param = ""

if _token_param:
    # Auto-configure Gemini from secrets (needed for AI evaluation on submission)
    _api_key_for_token = st.secrets.get("gemini_api_key", "")
    if _api_key_for_token and not st.session_state.get("genai_client"):
        try:
            configure_genai(_api_key_for_token)
            st.session_state.api_configured = True
        except Exception:
            pass

    # Resolve best available model for the token page
    if not st.session_state.get("selected_model"):
        _token_model = "models/gemini-2.0-flash"
        _token_client_tmp = st.session_state.get("genai_client")
        if _token_client_tmp:
            try:
                _available = [m.name for m in _token_client_tmp.models.list() if "gemini" in m.name.lower()]
                if _available:
                    _token_model = _available[0]
            except Exception:
                pass
        st.session_state.selected_model = _token_model

    st.markdown("## 🧭 Guiding North — Training Scenario")
    st.divider()

    # Look up the assignment
    try:
        assignment = get_assignment_by_token(_token_param)
    except Exception as _e:
        st.error(f"⚠️ Could not retrieve scenario: {_e}")
        st.stop()

    if not assignment:
        st.error("⚠️ This link is invalid or has already been used.")
        st.info("If you believe this is a mistake, please contact your supervisor for a new link.")
        st.stop()

    if assignment.get("token_used") or assignment.get("status") in ("completed", "reviewed"):
        st.success("✅ You have already submitted a response for this scenario.")
        st.info("Your supervisor will review your response and provide feedback. You can close this page.")
        st.stop()

    col_info1, col_info2, col_info3 = st.columns(3)
    with col_info1:
        st.markdown(f"**Assigned by:** {assignment.get('supervisor_name', 'Your Supervisor')}")
    with col_info2:
        st.markdown(f"**Role:** {assignment.get('assigned_role', 'N/A')}")
    with col_info3:
        st.markdown(f"**Topic:** {assignment.get('topic', 'N/A')}")
        if assignment.get('difficulty'):
            st.caption(f"Difficulty: {assignment.get('difficulty')}")

    st.divider()
    st.subheader("📋 Your Scenario")
    st.info(assignment.get("scenario") or "Scenario text not available.")

    st.divider()
    st.subheader("✍️ Your Response")
    st.caption("Read the scenario carefully, then write your response as if you were handling the situation in real life.")
    token_user_response = st.text_area(
        "Type your response here:",
        height=300,
        key="token_page_response",
        placeholder="Describe how you would handle this situation, what you would say, and what steps you would take..."
    )

    if st.button("📤 Submit Response", type="primary", key="token_submit_btn"):
        if not token_user_response.strip():
            st.warning("Please write your response before submitting.")
        else:
            with st.spinner("Submitting and evaluating your response..."):
                _token_client = st.session_state.get("genai_client")
                _token_analysis = None
                _token_eval_error = None
                if _token_client:
                    try:
                        _token_kb = load_knowledge_base()
                        _token_fw = load_framework()
                        _token_eval_prompt = f"""You are evaluating a staff response using the Guiding NORTH rubric.

**Framework:**
{_token_fw}

**Operational Knowledge Base:**
{_token_kb}
{retrieve_sop_context(f"{assignment.get('assigned_role','')} {assignment.get('scenario','')[:300]}")}

**Context:**
- Role: {assignment.get('assigned_role', 'Staff')}
- Scenario: {assignment.get('scenario', '')}
- Staff Response: {token_user_response}

Evaluate the response using the Guiding NORTH rubric. Provide:
1. An Overall Score (1–4)
2. A rating and justification for each pillar (N, O, R, T, H)
3. Specific suggestions for improvement
4. A full Exemplary Response Example showing an ideal response

**Output Format:**
OVERALL_SCORE: [1-4]

**Overall Score:** [1-4]

**N - Navigate Needs:**
- **Rating:** [Needs Development | Proficient | Exemplary]
- **Justification:** [justification]

**O - Own the Outcome:**
- **Rating:** [Needs Development | Proficient | Exemplary]
- **Justification:** [justification]

**R - Respond Respectfully:**
- **Rating:** [Needs Development | Proficient | Exemplary]
- **Justification:** [justification]

**T - Timely & Truthful:**
- **Rating:** [Needs Development | Proficient | Exemplary]
- **Justification:** [justification]

**H - Help Proactively:**
- **Rating:** [Needs Development | Proficient | Exemplary]
- **Justification:** [justification]

**Suggestions for Improvement:**
[suggestions]

**Exemplary Response Example:**
[full exemplary response]"""
                        _token_result = _token_client.models.generate_content(
                            model=st.session_state.get("selected_model", "models/gemini-2.0-flash"),
                            contents=_token_eval_prompt,
                            config=types.GenerateContentConfig(temperature=0.5, max_output_tokens=8000)
                        )
                        _token_analysis = _token_result.text if _token_result.text else None
                    except Exception as _eval_err:
                        _token_eval_error = str(_eval_err)
                else:
                    _token_eval_error = "Gemini API client not available."

                if save_assignment_response(assignment["id"], token_user_response, _token_analysis or ""):
                    mark_token_used(assignment["id"])
                    st.success("✅ Your response has been submitted successfully!")
                    if _token_eval_error:
                        st.warning(f"Note: AI evaluation could not run ({_token_eval_error}). Your supervisor can re-run it from the Results tab.")
                    st.balloons()
                    st.info("Your supervisor will review your response and provide feedback. You can close this page.")
                else:
                    st.error("There was a problem submitting your response. Please try again or contact your supervisor.")
    # Always stop here — never render the normal app sidebar/content
    st.stop()
# ─────────────────────────────────────────────────────────────────────────────


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
                save_user(
                    email=admin_email,
                    password=admin_password,
                    is_admin=True,
                    first_name="Admin",
                    last_name="Account",
                    position="Administrator"
                )
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
    elif not check_password_hash(users_db[email_input]["password_hash"], password_input):
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
                    if not check_password_hash(users_db[st.session_state.email]["password_hash"], current_pwd):
                        st.error("Current password is incorrect.")
                    elif len(new_pwd) < 6:
                        st.error("New password must be at least 6 characters.")
                    elif new_pwd != new_pwd_confirm:
                        st.error("New passwords do not match.")
                    else:
                        # We need to preserve the user's other data
                        user_data = users_db[st.session_state.email]
                        save_user(
                            email=st.session_state.email,
                            password=new_pwd,
                            is_admin=user_data.get('is_admin', False),
                            first_name=user_data.get('first_name', ''),
                            last_name=user_data.get('last_name', ''),
                            position=user_data.get('position', '')
                        )
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
                        save_user(
                            email=new_email,
                            password=new_pwd_admin,
                            is_admin=new_is_admin,
                            first_name=new_first,
                            last_name=new_last,
                            position=new_position
                        )
                        st.success(f"✅ User {new_email} created with temporary password!")
                        # No need to rerun, just clear the fields if desired or show success
                        # To refresh the user list, you might need to call load_users() again
                        # and update the state if you're displaying the list of users.
                        # For now, a success message is sufficient.
            
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
                                # We need to preserve the user's other data
                                user_data = users_db[user_to_manage]
                                save_user(
                                    email=user_to_manage,
                                    password=temp_pwd,
                                    is_admin=user_data.get('is_admin', False),
                                    first_name=user_data.get('first_name', ''),
                                    last_name=user_data.get('last_name', ''),
                                    position=user_data.get('position', '')
                                )
                                st.success(f"✅ Password reset! Temporary password: `{temp_pwd}`")
                            
                            if user_to_manage != st.session_state.email:
                                if st.button("Delete User", key="delete_user_btn"):
                                    if delete_user(user_to_manage):
                                        st.success(f"✅ User {user_to_manage} deleted.")
                                        st.rerun()
                else:
                    st.info("No users to manage.")
    
    if st.sidebar.button("Logout", key="logout_btn"):
        # Preserve essential keys across sessions
        keys_to_preserve = ['api_configured', 'selected_model', 'api_key', 'genai_client', 'models']
        for key in list(st.session_state.keys()):
            if key not in keys_to_preserve:
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
                "Assigned Scenarios",
                "Pending Review",
                "Guiding NORTH Framework",
                "Org Chart",
                "Results & Progress"
            ]
            tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(tab_names)
            assign_scenarios_tab = tab3
            assigned_scenarios_tab = tab4
            pending_review_tab = tab5
            framework_tab = tab6
            org_chart_tab = tab7
            config_tab = None
            results_tab = tab8
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
            st.warning("No staff roles configured. Please add roles in the **Configuration** tab.")
            _tab1_ready = False
        else:
            # Admin can practice as any role, supervisors can practice as their direct reports
            if st.session_state.get("is_admin"):
                available_roles = list(STAFF_ROLES.keys())
            elif st.session_state.get("user_role") == "supervisor":
                available_roles = [st.session_state.position] + st.session_state.get('direct_reports', [])
            else:
                available_roles = [st.session_state.position]
            
            # Ensure the list only contains valid roles from STAFF_ROLES
            available_roles = [role for role in available_roles if role in STAFF_ROLES]

            if not available_roles:
                st.warning("No roles available for you to simulate. Please check the configuration.")
                _tab1_ready = False
            else:
                _tab1_ready = True

        if _tab1_ready:
            selected_role = st.selectbox("Select Your Role:", available_roles, key="role_selector")
            difficulty = st.selectbox(
                "Select Scenario Difficulty:",
                ("Standard", "Challenging", "Complex"),
                key="difficulty_selector"
            )

        if _tab1_ready and selected_role in STAFF_ROLES:
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
                {load_knowledge_base()}
                {retrieve_sop_context(f'{selected_role} {selected_topic}')}
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

                **Task:** Generate a single, detailed, and realistic scenario for a '{selected_role}'. The difficulty of this scenario should be '{difficulty}'.

                **Source Priority for Scenario Content:**
                - Draw directly from the **Operational Knowledge Base** and **Relevant SOP Procedures** above when crafting the situation — use actual procedures, workflows, policies, and constraints described in those documents to make the scenario grounded in real HRL operations.
                - Use the **Guiding NORTH Framework** to ensure the scenario tests one or more of the five pillars (N, O, R, T, H).
                - Use the **Role Description** and **HRL Knowledge Base hours/constraints** to ensure the scenario is realistic for what this staff member would actually encounter given their role, schedule, and responsibilities.

                **Critical Requirements:**
                1. **Student Name:** Use a diverse, realistic first name that is NOT the same as in the previous scenario. Choose from diverse names like: Alex, Jordan, Casey, Morgan, Avery, Quinn, Jamie, Riley, Taylor, Chris, Sam, Pat, Blake, Drew, Devon, or create another realistic diverse name. Ensure the name changes every time.
                2. **UND Housing Realism — Use the Knowledge Base and SOPs:**
                   - Reference specific UND residence halls (McVey, West, Brannon, Noren, Selke, Smith, Johnstone, University Place, Swanson) or apartments (Berkeley Drive, Carleton Court, Hamline Square, etc.)
                   - Base all policies, fees, hours, procedures, and constraints on what is stated in the Operational Knowledge Base and SOP Procedures provided above — do NOT invent or assume details not present in those documents
                   - Reference real resources mentioned in the Knowledge Base (Wilkerson Service Center, Housing Self-Service portal, RA on Duty, etc.)
                   - Make scenarios feel like actual situations at UND Housing & Residence Life
                3. **Variety Requirement:** Do NOT repeat the same type of scenario as the previous one. Focus on different residential life issues.
                4. **Building/Location Variety:** IMPORTANT - Do NOT repeat the same building as the previous scenario. Vary buildings across all available options:
                   - Residence Halls: McVey Hall, West Hall, Brannon Hall, Noren Hall, Selke Hall, Smith Hall, Johnstone Hall, University Place, Swanson Hall
                   - Apartments: Berkeley Drive, Carleton Court, Hamline Square, Mt. Vernon/Williamsburg, Swanson Complex, Tulane Court, Virginia Rose, 3904 University Ave
                   - Each scenario should use a DIFFERENT building/location from the previous scenario to ensure comprehensive campus coverage
                5. **Scenario Type:** Pick from these areas (rotate through them, avoiding the previous type):
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

                The scenario should be a full, detailed paragraph that is realistic and something this person would likely encounter in their role at UND Housing. It must be designed to test their proficiency in one or more pillars of the Guiding NORTH framework. Include the student's name, specific details, and contextual information to make it engaging and realistic.
                
                **IMPORTANT:** Do NOT include any concluding sentence that explains the scenario or explains why it might be challenging. Present only the scenario itself.
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

            if st.button("🤖 Evaluate My Response", key="evaluate_response_button"):
                if user_response:
                    with st.spinner("Evaluating your response..."):
                        role_info = STAFF_ROLES[selected_role]
                        eval_prompt = f"""
                        **System Grounding:** You are an expert training assistant for the University of North Dakota Housing & Residence Life, specializing in the Guiding NORTH Framework. Your analysis MUST be based *strictly* on the following framework document:

                        ---
                        {GUIDING_NORTH_FRAMEWORK}
                        ---

                        **Operational Knowledge Base (protocols, policies & supervisor-approved exemplary standards):**
                        ---
                        {load_knowledge_base()}
                        {retrieve_sop_context(f'{selected_role} {st.session_state.get("scenario", "")[:300]}')}
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
                            st.session_state.evaluation = evaluation_response.text
                            # Save result to DB for supervisor review
                            overall_score = "Not Found"
                            for line in evaluation_response.text.splitlines():
                                m = re.search(r"OVERALL_SCORE\s*:\s*([1-4])", line)
                                if m:
                                    overall_score = m.group(1)
                                    break
                            save_results({
                                "first_name": st.session_state.get("first_name", ""),
                                "last_name": st.session_state.get("last_name", ""),
                                "email": st.session_state.get("email", ""),
                                "timestamp": datetime.now().isoformat(),
                                "role": selected_role,
                                "difficulty": difficulty,
                                "scenario": st.session_state.scenario,
                                "user_response": user_response,
                                "evaluation": evaluation_response.text,
                                "overall_score": overall_score,
                                "exemplary_response": extract_exemplary_response(evaluation_response.text),
                            })
                        except Exception as e:
                            st.error(f"Error evaluating response: {e}")
                else:
                    st.warning("Please enter your response before evaluating.")

        if st.session_state.evaluation:
            st.markdown("---")
            st.markdown("### 💡 AI Evaluation & Feedback")
            st.markdown(st.session_state.evaluation)
            if st.button("Try Another Scenario", key="clear_scenario_btn"):
                st.session_state.scenario = ""
                st.session_state.evaluation = ""
                st.rerun()

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
            
            # Staff selector — auto-fills fields from DB
            call_users_db = load_users()
            call_staff_options = {"-- Select a staff member --": None}
            for _email, _u in sorted(call_users_db.items(), key=lambda x: (x[1].get('last_name',''), x[1].get('first_name',''))):
                _label = f"{_u.get('first_name','')} {_u.get('last_name','')} ({_email})".strip()
                call_staff_options[_label] = _email

            selected_staff_label = st.selectbox(
                "Select Staff Member:",
                options=list(call_staff_options.keys()),
                key="call_staff_selector"
            )
            selected_staff_email = call_staff_options[selected_staff_label]

            if selected_staff_email:
                _sd = call_users_db[selected_staff_email]
                call_first_name = _sd.get("first_name", "")
                call_last_name  = _sd.get("last_name", "")
                call_email      = selected_staff_email
                _default_role   = _sd.get("position", "")
                _role_options   = list(STAFF_ROLES.keys())
                _role_index     = _role_options.index(_default_role) if _default_role in _role_options else 0
                call_role = st.selectbox("Role:", _role_options, index=_role_index, key="call_role")
            else:
                call_first_name = ""
                call_last_name  = ""
                call_email      = ""
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

                            **Operational Knowledge Base (protocols, policies & supervisor-approved exemplary standards):**
                            ---
                            {load_knowledge_base()}
                            {retrieve_sop_context(f'{call_role} {call_transcript[:300]}')}
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
                                        "overall_score": overall_score,
                                        "exemplary_response": extract_exemplary_response(analysis_response.text),
                                    }
                                    if save_results(new_result):
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

                                    **Operational Knowledge Base (protocols, policies & supervisor-approved exemplary standards):**
                                    ---
                                    {load_knowledge_base()}
                                    {retrieve_sop_context(call_role)}
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
                                            "overall_score": overall_score,
                                            "exemplary_response": extract_exemplary_response(analysis_response.text),
                                        }
                                        if save_results(new_result):
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
                    selected_difficulty = st.selectbox(
                        "Select difficulty level:",
                        options=["Standard", "Challenging", "Complex"],
                        key="assign_scenario_difficulty"
                    )
                
                # Generate scenario button
                if st.button("Generate and Assign Scenario", key="generate_assign_scenario_btn"):
                    if not selected_staff:
                        st.error("Please select at least one staff member.")
                    else:
                        with st.spinner(f"Generating {selected_difficulty} {selected_topic} scenario for {len(selected_staff)} staff member(s)..."):
                            try:
                                # Generate the scenario
                                scenario_prompt = f"""Generate a realistic housing and residence life training scenario for the role: {selected_role}.

SCENARIO REQUIREMENTS:
Topic: {selected_topic}
Difficulty: {selected_difficulty}

Difficulty guidance:
- Standard: A straightforward, single-issue situation a new staff member could handle with basic training.
- Challenging: A more nuanced situation involving multiple considerations, competing priorities, or an escalating student.
- Complex: A high-stakes, multi-faceted situation requiring advanced judgment, policy knowledge, and de-escalation skills.

USE THIS AUTHENTIC UND HOUSING INFORMATION:
{UND_HOUSING_CONTEXT}

The scenario should:
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

Keep the scenario concise but realistic. Present only the scenario and task without any concluding commentary."""

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
                                
                                # Save the assignment and collect tokens for link display
                                all_users_db = load_users()
                                _assign_app_url = load_config().get("app_url", "").rstrip("/")
                                _assign_links = []
                                for staff_email in selected_staff:
                                    user_data = all_users_db.get(staff_email, {})
                                    _token = save_assignment(
                                        email=staff_email,
                                        scenario_name=selected_topic,
                                        supervisor_email=st.session_state.get("email"),
                                        supervisor_name=f"{st.session_state.get('first_name', '')} {st.session_state.get('last_name', '')}".strip(),
                                        staff_name=f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip() or staff_email,
                                        assigned_role=selected_role,
                                        scenario_text=generated_scenario,
                                        difficulty=selected_difficulty
                                    )
                                    if _token:
                                        _staff_name = f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip() or staff_email
                                        if _assign_app_url:
                                            _link = f"{_assign_app_url}/?token={_token}"
                                        else:
                                            _link = f"?token={_token}"
                                        _assign_links.append((_staff_name, staff_email, _link))

                                st.success(f"✅ Scenario assigned to {len(selected_staff)} staff member(s)!")

                                if _assign_links:
                                    st.subheader("🔗 Shareable Links")
                                    st.caption("Send these links directly to each staff member. They can complete the scenario without logging in.")
                                    if not _assign_app_url:
                                        st.warning("⚠️ App URL not configured — links show only the token portion. Go to **Configuration → App URL** to set your full app address.")
                                    for _name, _email, _link in _assign_links:
                                        st.markdown(f"**{_name}** ({_email})")
                                        st.code(_link, language=None)
                                else:
                                    st.info("They will see the scenario in their \"Assigned Scenarios\" section.")
                                    
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
                (idx, a) for idx, a in enumerate(assignments_data)
                if a.get("status") == "completed"
                and a.get("email") in visible_users
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

                        # ── Exemplary Response Review ──────────────────────────
                        exemplary = result.get('exemplary_refined') or result.get('exemplary_response')
                        st.divider()
                        st.subheader("🌟 Review AI Exemplary Response")
                        st.markdown("#### Current AI Exemplary Response")
                        if exemplary:
                            st.info(exemplary)
                        else:
                            st.warning("No exemplary response was extracted from this evaluation. You can paste one below to start the review process.")
                            exemplary = ""

                        st.markdown("#### Your Corrections / Annotations")
                        st.caption("Describe anything the AI got wrong, missed, or should emphasize differently. You can also paste a corrected version directly.")
                        feedback_val = result.get('exemplary_feedback') or ""
                        exemplary_feedback = st.text_area(
                            "Corrections:",
                            value=feedback_val,
                            height=150,
                            key=f"ex_feedback_{idx}_{result.get('id')}"
                        )

                        refine_col, save_col = st.columns(2)
                        with refine_col:
                            if st.button("🤖 Refine with AI", key=f"refine_ex_{idx}_{result.get('id')}"):
                                if exemplary_feedback.strip():
                                    with st.spinner("Refining exemplary response..."):
                                        try:
                                            if exemplary:
                                                refine_prompt = f"""You previously wrote an exemplary response example for a housing & residence life training scenario/call. A supervisor has reviewed it and provided corrections.

SCENARIO / CALL CONTEXT:
{result.get('scenario', '')}

YOUR ORIGINAL EXEMPLARY RESPONSE:
{exemplary}

SUPERVISOR CORRECTIONS / ANNOTATIONS:
{exemplary_feedback}

Please rewrite the exemplary response incorporating the supervisor's corrections. Keep the same structure and UND-specific context but fix the issues identified. Output only the revised exemplary response text."""
                                            else:
                                                refine_prompt = f"""Generate an exemplary response example for the following housing & residence life training scenario/call, taking the supervisor's notes into account.

SCENARIO / CALL CONTEXT:
{result.get('scenario', '')}

AI EVALUATION SUMMARY:
{result.get('evaluation', '')[:2000]}

SUPERVISOR NOTES:
{exemplary_feedback}

Output only the exemplary response text."""
                                            refine_result = client.models.generate_content(
                                                model=st.session_state.get("selected_model", "models/gemini-1.5-flash"),
                                                contents=refine_prompt
                                            )
                                            refined_text = refine_result.text if refine_result.text else ""
                                            if update_result(
                                                result.get('id'),
                                                exemplary_feedback=exemplary_feedback,
                                                exemplary_refined=refined_text
                                            ):
                                                sync_corrections_to_knowledge_base()
                                                st.success("✅ Exemplary response refined and saved!")
                                                st.rerun()
                                            else:
                                                st.error("Failed to save refined response.")
                                        except Exception as e:
                                            st.error(f"Error refining response: {e}")
                                else:
                                    st.warning("Please add your corrections before refining.")
                        with save_col:
                            if st.button("💾 Save Corrections Only", key=f"save_ex_{idx}_{result.get('id')}"):
                                if update_result(result.get('id'), exemplary_feedback=exemplary_feedback):
                                    sync_corrections_to_knowledge_base()
                                    st.success("Corrections saved.")
                                    st.rerun()
                        # ──────────────────────────────────────────────────────

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
                                if update_result(
                                    result.get('id'),
                                    status='completed',
                                    reviewed_by=st.session_state.email,
                                    review_date=datetime.now().isoformat(),
                                    supervisor_notes=supervisor_notes
                                ):
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
                                if update_assignment_status(assignment.get('id'), 'reviewed', supervisor_feedback):
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
                a for a in assignments_data
                if a.get("email") == staff_email
            ]
            
            if not my_assignments:
                st.info("No assigned scenarios yet. Check back soon for new training assignments from your supervisor!")
            else:
                # Tabs for pending and completed
                pending_tab, completed_tab = st.tabs(["Pending", "Completed"])
                
                with pending_tab:
                    pending_assignments = [a for a in my_assignments if a.get("status") == "assigned"]
                    
                    if not pending_assignments:
                        st.info("All assigned scenarios completed!")
                    else:
                        for assignment in pending_assignments:
                            with st.expander(f"📋 {assignment.get('topic')} (Assigned by {assignment.get('supervisor_name')}) - {assignment.get('assigned_date', 'Unknown')[:10]}"):
                                st.markdown("### Scenario:")
                                st.info(assignment.get("scenario", "No scenario text available."))

                                col1, col2 = st.columns([3, 1])
                                with col1:
                                    response_key = f"response_{assignment.get('id')}"
                                    user_response = st.text_area(
                                        "Your Response:",
                                        height=200,
                                        key=response_key,
                                        placeholder="Type your response to this scenario here..."
                                    )
                                    if st.button("Submit Response", key=f"submit_assignment_{assignment.get('id')}"):
                                        if user_response.strip():
                                            try:
                                                with st.spinner("Analyzing your response with AI..."):
                                                    analysis_prompt = f"""Evaluate this staff response using the Guiding NORTH framework.
Role: {assignment.get('assigned_role', 'Staff')}
Scenario: {assignment.get('scenario', '')}
Response: {user_response}
Provide structured feedback on each NORTH pillar and an overall score (1-4)."""
                                                    ai_result = client.models.generate_content(
                                                        model=st.session_state.get("selected_model", "models/gemini-1.5-flash"),
                                                        contents=analysis_prompt
                                                    )
                                                    ai_analysis = ai_result.text if ai_result.text else "Unable to analyze response."
                                                save_assignment_response(assignment.get('id'), user_response, ai_analysis)
                                                st.success("✅ Response submitted successfully!")
                                                st.rerun()
                                            except Exception as e:
                                                st.error(f"Error analyzing response: {e}")
                                        else:
                                            st.warning("Please enter your response.")

                                with col2:
                                    if st.button("Delete Assignment", key=f"delete_assignment_{assignment.get('id')}"):
                                        if delete_assignment(assignment.get('id')):
                                            st.success("Assignment removed.")
                                            st.rerun()
                
                with completed_tab:
                    completed_assignments = [a for a in my_assignments if a.get("status") in ("completed", "reviewed")]
                    
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
            st.warning("No staff roles defined. Please add roles in the Configuration tab.")
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

            st.divider()

            # App URL Setting
            st.subheader("🔗 App URL (for Shareable Links)")
            st.caption("Set the public URL of this app so shareable scenario links work correctly. Example: https://yourapp.streamlit.app")
            _current_app_url = load_config().get("app_url", "")
            _new_app_url = st.text_input("App Base URL:", value=_current_app_url, placeholder="https://yourapp.streamlit.app", key="app_url_input")
            if st.button("💾 Save App URL", key="save_app_url_btn"):
                _cfg = load_config()
                _cfg["app_url"] = _new_app_url.strip().rstrip("/")
                if save_config(_cfg):
                    st.success("✅ App URL saved!")
                else:
                    st.error("Failed to save App URL.")

            st.divider()

            # SOP Manual Upload
            st.subheader("📋 SOP Manual Upload")
            st.caption("Upload PDF copies of your Standard Operating Procedures. The AI will retrieve relevant sections when generating evaluations.")

            try:
                import pypdf
                _pypdf_available = True
            except ImportError:
                try:
                    import PyPDF2 as _pypdf_compat
                    _pypdf_available = False
                except ImportError:
                    _pypdf_available = None

            sop_docs = list_sop_documents()
            if sop_docs:
                st.markdown("**Uploaded Documents:**")
                for _doc in sop_docs:
                    _col1, _col2, _col3 = st.columns([4, 1, 1])
                    with _col1:
                        st.markdown(f"📄 **{_doc['doc_name']}** — {_doc['chunk_count']} chunks")
                    with _col2:
                        _view_key = f"view_sop_{_doc['doc_name']}"
                        if st.button("👁️ View", key=_view_key):
                            st.session_state[f"show_chunks_{_doc['doc_name']}"] = not st.session_state.get(f"show_chunks_{_doc['doc_name']}", False)
                    with _col3:
                        if st.button("🗑️ Delete", key=f"del_sop_{_doc['doc_name']}"):
                            if delete_sop_document(_doc['doc_name']):
                                st.success(f"Deleted {_doc['doc_name']}")
                                st.rerun()
                    if st.session_state.get(f"show_chunks_{_doc['doc_name']}", False):
                        with st.expander(f"Chunks — {_doc['doc_name']}", expanded=True):
                            _chunks_data = get_sop_chunks_for_doc(_doc['doc_name'])
                            _search_filter = st.text_input(
                                "Filter chunks (text search):",
                                key=f"chunk_filter_{_doc['doc_name']}",
                                placeholder="Type to filter..."
                            )
                            _shown = 0
                            for _cidx, _ctext in _chunks_data:
                                if _search_filter and _search_filter.lower() not in _ctext.lower():
                                    continue
                                st.markdown(f"**Chunk {_cidx}**")
                                st.text(_ctext[:800] + ("..." if len(_ctext) > 800 else ""))
                                st.divider()
                                _shown += 1
                            if _shown == 0:
                                st.info("No chunks match that filter.")
            else:
                st.info("No SOP documents uploaded yet.")

            st.markdown("**Upload New Document:**")
            _sop_upload = st.file_uploader(
                "Choose PDF file(s)",
                type=["pdf"],
                accept_multiple_files=True,
                key="sop_pdf_uploader"
            )
            if _sop_upload:
                if st.button("⬆️ Process & Store SOP", key="process_sop_btn"):
                    for _uploaded_pdf in _sop_upload:
                        with st.spinner(f"Processing {_uploaded_pdf.name}..."):
                            try:
                                _pdf_text_parts = []
                                if _pypdf_available:
                                    import pypdf as _pypdf_mod
                                    _reader = _pypdf_mod.PdfReader(_uploaded_pdf)
                                    for _page in _reader.pages:
                                        _page_text = _page.extract_text()
                                        if _page_text:
                                            _pdf_text_parts.append(_page_text)
                                elif _pypdf_available is False:
                                    import PyPDF2 as _pypdf2_mod
                                    _reader = _pypdf2_mod.PdfReader(_uploaded_pdf)
                                    for _page in _reader.pages:
                                        _page_text = _page.extract_text()
                                        if _page_text:
                                            _pdf_text_parts.append(_page_text)
                                else:
                                    st.error("pypdf or PyPDF2 is required. Run: pip install pypdf")
                                    continue

                                _full_text = "\n\n".join(_pdf_text_parts)
                                _chunks = chunk_text(_full_text, chunk_size=500, overlap=50)
                                if store_sop_chunks(_uploaded_pdf.name, _chunks):
                                    st.success(f"✅ Stored **{_uploaded_pdf.name}** — {len(_chunks)} chunks indexed for search")
                                else:
                                    st.error(f"Failed to store {_uploaded_pdf.name}")
                            except Exception as _sop_err:
                                st.error(f"Error processing {_uploaded_pdf.name}: {_sop_err}")

            st.divider()

            # Knowledge Base Editor
            st.divider()
            st.subheader("📖 HRL Knowledge Base Editor")
            st.caption("Edit the authoritative knowledge base used by the AI for all evaluations. The auto-generated supervisor corrections section at the bottom is managed automatically — manual edits above that marker are safe.")
            with st.expander("Edit HRL Knowledge Base", expanded=False):
                kb_content = load_knowledge_base()
                edited_kb = st.text_area(
                    "Knowledge Base Content:",
                    value=kb_content,
                    height=500,
                    key="kb_editor_content"
                )
                kb_col1, kb_col2 = st.columns([1, 3])
                with kb_col1:
                    if st.button("💾 Save Knowledge Base", key="save_kb_btn", type="primary"):
                        try:
                            with open(KNOWLEDGE_BASE_FILE, 'w', encoding='utf-8') as f:
                                f.write(edited_kb)
                            st.success("✅ Knowledge Base saved successfully!")
                        except Exception as e:
                            st.error(f"Failed to save: {e}")
                with kb_col2:
                    st.caption("⚠️ Saving will overwrite the file. The supervisor corrections section will be re-appended on the next correction save.")

            # Correction Library Section
            st.divider()
            st.subheader("📚 Exemplary Correction Library")
            st.caption("All supervisor-refined exemplary responses. These are automatically used as quality benchmarks when the AI generates future exemplary responses.")
            correction_examples = load_exemplary_examples(limit=50)
            if not correction_examples:
                st.info("No supervisor-refined exemplary responses yet. Use the 'Refine with AI' feature in Pending Review or Results & Progress to build your library.")
            else:
                st.success(f"✅ {len(correction_examples)} approved exemplary response(s) in the library. The AI learns from all of them.")
                for j, ex in enumerate(correction_examples, 1):
                    review_date = ex.get('review_date', '')
                    date_str = str(review_date)[:10] if review_date else "Unknown date"
                    reviewer = ex.get('reviewed_by', 'Unknown reviewer')
                    scenario_preview = (ex.get('scenario') or '')[:80]
                    with st.expander(f"Example {j} — {date_str} — {reviewer} — {scenario_preview}...", expanded=False):
                        st.markdown("**Scenario Context:**")
                        st.info(ex.get('scenario') or 'N/A')
                        if ex.get('exemplary_response'):
                            st.markdown("**Original AI Exemplary:**")
                            st.markdown(ex.get('exemplary_response'))
                        if ex.get('exemplary_feedback'):
                            st.markdown("**Supervisor Corrections Applied:**")
                            st.warning(ex.get('exemplary_feedback'))
                        st.markdown("**✅ Final Approved Exemplary Response:**")
                        st.success(ex.get('exemplary_refined') or 'N/A')

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
        for assignment in assignments_data:
            if assignment.get("status") in ("completed", "reviewed"):
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
                            update_result(res.get('id'), overall_score=parsed_score)
                            updated_results += 1

                    assignments_data = load_assignments()
                    updated_assignments = 0
                    for assignment in assignments_data:
                        analysis_text = assignment.get("ai_analysis", "")
                        parsed_score = parse_overall_score(analysis_text)
                        if parsed_score and (not is_valid_score(assignment.get("overall_score")) or assignment.get("overall_score") != parsed_score):
                            assignment["overall_score"] = parsed_score
                            updated_assignments += 1

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
                                    (a for a in assignments_data_updated if str(a.get("id")) == assignment_id),
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
                                    # Persist updated analysis to DB
                                    save_assignment_response(
                                        assignment.get('id'),
                                        assignment.get('response', ''),
                                        analysis_text
                                    )
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
                                    update_result(res.get('id'), evaluation=analysis_text, overall_score=res.get('overall_score'))
                                    updated_results += 1
                                except Exception:
                                    errors += 1

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
                                            if delete_assignment(result.get("assignment_id")):
                                                st.success("Result deleted.")
                                                st.rerun()
                                        else:
                                            if result.get('id'):
                                                delete_result(result.get('id'))
                                            else:
                                                # Fallback: match by email+timestamp
                                                results_data_updated = load_results()
                                                matched = next(
                                                    (r for r in results_data_updated
                                                     if r.get('email') == result.get('email')
                                                     and r.get('timestamp') == result.get('timestamp')),
                                                    None
                                                )
                                                if matched and matched.get('id'):
                                                    delete_result(matched.get('id'))

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

                                # Show / edit exemplary response
                                exemplary_to_show = result.get('exemplary_refined') or result.get('exemplary_response')
                                can_edit_exemplary = (
                                    (st.session_state.get('is_admin') or st.session_state.get('user_role') == 'supervisor')
                                    and not result.get('is_assigned')
                                    and result.get('id')
                                )
                                st.markdown("---")
                                st.markdown("#### 🌟 Exemplary Response")
                                if exemplary_to_show:
                                    label = "Supervisor-Refined" if result.get('exemplary_refined') else "AI Generated"
                                    st.caption(label)
                                    st.success(exemplary_to_show)
                                    if result.get('exemplary_feedback'):
                                        st.markdown("**Supervisor Corrections Applied:**")
                                        st.caption(result.get('exemplary_feedback'))
                                else:
                                    st.warning("No exemplary response has been extracted yet.")

                                if can_edit_exemplary:
                                    st.markdown("**Edit Exemplary Response**")
                                    rp_feedback_val = result.get('exemplary_feedback') or ""
                                    rp_exemplary_feedback = st.text_area(
                                        "Your Corrections / Annotations:",
                                        value=rp_feedback_val,
                                        height=120,
                                        key=f"rp_ex_feedback_{i}_{result.get('id')}"
                                    )
                                    rp_col1, rp_col2 = st.columns(2)
                                    with rp_col1:
                                        if st.button("🤖 Refine with AI", key=f"rp_refine_{i}_{result.get('id')}"):
                                            if rp_exemplary_feedback.strip():
                                                with st.spinner("Refining exemplary response..."):
                                                    try:
                                                        if exemplary_to_show:
                                                            rp_prompt = f"""You previously wrote an exemplary response example for a housing & residence life training scenario/call. A supervisor has reviewed it and provided corrections.

SCENARIO / CALL CONTEXT:
{result.get('scenario', '')}

YOUR ORIGINAL EXEMPLARY RESPONSE:
{exemplary_to_show}

SUPERVISOR CORRECTIONS / ANNOTATIONS:
{rp_exemplary_feedback}

Please rewrite the exemplary response incorporating the supervisor's corrections. Keep the same structure and UND-specific context but fix the issues identified. Output only the revised exemplary response text."""
                                                        else:
                                                            rp_prompt = f"""Generate an exemplary response example for the following housing & residence life training scenario/call, taking the supervisor's notes into account.

SCENARIO / CALL CONTEXT:
{result.get('scenario', '')}

AI EVALUATION SUMMARY:
{result.get('evaluation', '')[:2000]}

SUPERVISOR NOTES:
{rp_exemplary_feedback}

Output only the exemplary response text."""
                                                        rp_refine_result = client.models.generate_content(
                                                            model=st.session_state.get("selected_model", "models/gemini-1.5-flash"),
                                                            contents=rp_prompt
                                                        )
                                                        rp_refined_text = rp_refine_result.text if rp_refine_result.text else ""
                                                        if update_result(
                                                            result.get('id'),
                                                            exemplary_feedback=rp_exemplary_feedback,
                                                            exemplary_refined=rp_refined_text
                                                        ):
                                                            sync_corrections_to_knowledge_base()
                                                            st.success("✅ Exemplary response refined and saved!")
                                                            st.rerun()
                                                        else:
                                                            st.error("Failed to save refined response.")
                                                    except Exception as e:
                                                        st.error(f"Error refining response: {e}")
                                            else:
                                                st.warning("Please add your corrections before refining.")
                                    with rp_col2:
                                        if st.button("💾 Save Corrections Only", key=f"rp_save_ex_{i}_{result.get('id')}"):
                                            if update_result(result.get('id'), exemplary_feedback=rp_exemplary_feedback):
                                                sync_corrections_to_knowledge_base()
                                                st.success("Corrections saved.")
                                                st.rerun()
                
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
