import psycopg2
import os
import toml

def get_db_connection_string():
    """Reads the Neon DB connection string from .streamlit/secrets.toml."""
    try:
        # Construct a path relative to the current working directory
        secrets_path = os.path.join(os.getcwd(), ".streamlit", "secrets.toml")
        print(f"Attempting to read secrets from: {secrets_path}")
        secrets = toml.load(secrets_path)
        connection_string = secrets.get("NEON_DB_CONNECTION_STRING")
        if not connection_string:
            print("NEON_DB_CONNECTION_STRING not found inside the toml file.")
            return None
        return connection_string
    except FileNotFoundError:
        print(f"Error: Secrets file not found at {secrets_path}")
        return None
    except Exception as e:
        print(f"Error reading secrets.toml: {e}")
        return None

def init_db():
    """Initialize the database and create tables if they don't exist."""
    db_connection_string = get_db_connection_string()
    if not db_connection_string:
        print("Database connection string not found. Aborting.")
        return

    conn = None
    try:
        conn = psycopg2.connect(db_connection_string)
        with conn.cursor() as cur:
            print("Creating 'users' table...")
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
            print("'users' table created or already exists.")

            print("Creating 'results' table...")
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
            print("'results' table created or already exists.")

            print("Creating 'scenario_assignments' table...")
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
            print("'scenario_assignments' table created or already exists.")

            print("Creating 'app_config' table...")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS app_config (
                    key VARCHAR(255) PRIMARY KEY,
                    value JSONB NOT NULL
                );
            """)
            print("'app_config' table created or already exists.")

            conn.commit()
            print("\\nDatabase setup completed successfully!")
    except Exception as e:
        print(f"Database initialization failed: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    init_db()
