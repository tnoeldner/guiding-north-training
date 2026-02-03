# 🧭 Guiding North Training Platform

An AI-powered training and practice platform for UND Housing & Residence Life staff, built with Streamlit and Google Gemini.

## Features

- **Scenario Simulator**: Practice handling realistic resident situations with AI-powered evaluation based on the Guiding North Framework
- **Tone Polisher**: Get AI feedback on communication tone and professionalism
- **Call Analysis**: Transcribe and analyze phone call interactions
- **Organizational Chart**: View department structure and reporting relationships
- **Results & Progress**: Track performance metrics, visualize improvements, and compare against peers
- **Admin Dashboard**: Manage staff roles, organizational structure, and user accounts
- **Password Authentication**: Secure account management with role-based access control

## Quick Start

### Local Development

1. **Clone the repository**
```bash
git clone https://github.com/YOUR-USERNAME/guiding-north-training.git
cd guiding-north-training
```

2. **Create virtual environment**
```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # macOS/Linux
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Set up Gemini API key**
Create `.streamlit/secrets.toml`:
```toml
gemini_api_key = "your-gemini-api-key-here"
```

5. **Run the app**
```bash
streamlit run app.py
```

### Cloud Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for complete Streamlit Cloud deployment instructions.

## System Requirements

- Python 3.9+
- Google Gemini API key (free tier available)
- Modern web browser

## Technology Stack

- **Frontend**: Streamlit
- **AI/LLM**: Google Generativeai (Gemini 2.5 Pro)
- **Data**: JSON-based (local) or cloud database
- **Visualization**: Plotly, streamlit-agraph
- **PDF Processing**: PyPDF2

## Documentation

- `DEPLOYMENT.md` - Cloud deployment guide
- `config.json` - Organizational structure and role definitions
- `guiding_north_framework.md` - Core framework documentation
- `housing_best_practices.md` - Best practices reference
- `und_housing_website.md` - Website and policies reference

## User Roles

### Staff
- Access: Scenario Simulator, Tone Polisher, Org Chart, Results & Progress
- Permissions: Practice scenarios, view own results only
- Cannot: Manage users or system configuration

### Admin
- Access: All features including Call Analysis and Configuration
- Permissions: Create users, manage roles, configure system, view all results
- Responsibilities: User management, system maintenance

## First-Time Setup

1. **Create Admin Account**
   - First login will prompt admin account creation
   - Email and secure password required

2. **Add Staff Members**
   - Use Admin Account Settings → New User tab
   - Set position/role and temporary password
   - Users must change password on first login

3. **Configure Organization**
   - Define staff roles and reporting relationships
   - Upload job descriptions via Configuration tab
   - Set up Guiding North framework references

## Key Features

### Scenario Practice
- Choose from 8+ staff roles
- Three difficulty levels: Foundational, Intermediate, Advanced
- Variety constraints ensure diverse scenarios
- AI evaluation based on Guiding North Framework pillars

### Analytics & Progress
- Score progression charts with trendlines
- Performance by difficulty level
- Role-based peer comparison
- Supervisor reports viewing

### Call Analysis
- Transcript analysis (text input)
- Audio transcription with Gemini native support
- Framework-based evaluation
- Detailed feedback on communication

## Security

- Password hashing with PBKDF2-SHA256
- Role-based access control
- Secure API key management via Streamlit Secrets
- Email validation
- Duplicate prevention

## Data Storage

**Local Development**: JSON files (users.json, results.json, config.json)

**Cloud Deployment**: Ephemeral storage (data resets on app restart)
- For persistent storage, upgrade to Streamlit Teams or use cloud database

## Support & Troubleshooting

See [DEPLOYMENT.md](DEPLOYMENT.md#troubleshooting) for common issues.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit changes
4. Push to GitHub
5. Create pull request

## License

Internal UND Housing & Residence Life Tool

---

**Platform Version**: 1.0  
**Last Updated**: February 2026
