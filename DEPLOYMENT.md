# Guiding North Training Platform - Deployment Guide

## Overview
This guide explains how to deploy the Guiding North Training Platform to Streamlit Cloud using GitHub.

## Prerequisites
- GitHub account
- Streamlit Cloud account (free tier available at https://streamlit.io/cloud)
- Google Gemini API key

## Deployment Steps

### 1. Prepare Your Repository

#### A. Create a GitHub Repository
1. Go to https://github.com/new
2. Create a new repository (e.g., `guiding-north-training`)
3. Clone it locally:
```bash
git clone https://github.com/YOUR-USERNAME/guiding-north-training.git
cd guiding-north-training
```

#### B. Push Code to GitHub
1. Copy all files from your local project to the repository
2. Ensure `.gitignore` includes sensitive files:
   - `.streamlit/secrets.toml`
   - `users.json`
   - `results.json`

3. Commit and push:
```bash
git add .
git commit -m "Initial commit: Guiding North Training Platform"
git push origin main
```

### 2. Set Up Streamlit Cloud

#### A. Connect to Streamlit Cloud
1. Go to https://share.streamlit.io
2. Click "New app"
3. Select:
   - **GitHub repo**: YOUR-USERNAME/guiding-north-training
   - **Branch**: main
   - **Main file path**: app.py
4. Click "Deploy"

#### B. Configure Secrets in Streamlit Cloud
Once deployed, add your Gemini API key:

1. Click the "..." menu in the top-right corner
2. Select "Settings"
3. Go to the "Secrets" section
4. Add your secrets in TOML format:

```toml
gemini_api_key = "your-actual-gemini-api-key-here"
```

5. Click "Save"

### 3. Verify Deployment

1. Your app should reload automatically
2. Check that the app initializes without API key input
3. Test login functionality
4. Test scenario creation and evaluation

## Local Development

For local development, create `.streamlit/secrets.toml`:

```toml
gemini_api_key = "your-test-api-key"
```

Run locally:
```bash
streamlit run app.py
```

**Important**: Never commit `secrets.toml` to GitHub. It's already in `.gitignore`.

## File Structure

```
guiding-north-training/
├── .streamlit/
│   └── secrets.toml (LOCAL ONLY - NOT COMMITTED)
├── .gitignore
├── app.py
├── config.json
├── requirements.txt
├── users.json (local data)
├── results.json (local data)
├── *.md (documentation files)
└── HRLKnowledgeBase (directory)
```

## Updating Your App

1. Make changes locally
2. Test with `streamlit run app.py`
3. Commit changes:
```bash
git add .
git commit -m "Update: description of changes"
git push origin main
```
4. Streamlit Cloud will automatically redeploy

## Environment Variables

### API Key Configuration
- **Streamlit Cloud**: Set via Secrets panel
- **Local Development**: Use `.streamlit/secrets.toml`
- **Access in code**: `st.secrets.get("gemini_api_key")`

## Data Persistence

⚠️ **Important**: Streamlit Cloud has ephemeral storage. This means:

- `users.json` and `results.json` will be reset when the app restarts
- For persistent storage, consider:
  - Upgrading to Streamlit Teams (paid)
  - Using a database (PostgreSQL, Firebase, etc.)
  - Using cloud storage (Google Cloud Storage, AWS S3)

### Option: Add Cloud Database

For persistent user and results data, add a database connection:

```python
# Example with Firebase/SQLite
import sqlite3

# Create a database in cloud storage
db_connection = connect_to_cloud_database()
```

Contact Streamlit support for database integration guidance.

## Troubleshooting

### App won't deploy
- Check `requirements.txt` has all dependencies
- Verify `app.py` is in root directory
- Check GitHub connection is authorized

### API key not working
- Verify key in Streamlit Cloud Secrets panel
- Test locally first with `.streamlit/secrets.toml`
- Check key has proper permissions for Gemini API

### Data not persisting
- This is expected on Streamlit Cloud (ephemeral storage)
- Use cloud database for persistent storage
- Local files work on personal machine only

### Import errors
- Run `pip install -r requirements.txt`
- Check all packages in requirements.txt are compatible
- Try `pip install --upgrade google-generativeai`

## Support

For issues:
1. Check Streamlit documentation: https://docs.streamlit.io
2. Check Gemini API docs: https://ai.google.dev
3. Review GitHub deployment logs in Streamlit Cloud

## Security Best Practices

✅ **Do:**
- Use `.gitignore` to protect secrets
- Rotate API keys regularly
- Use Streamlit Cloud Secrets for production
- Enable GitHub two-factor authentication

❌ **Don't:**
- Commit `.streamlit/secrets.toml` to GitHub
- Share API keys in code or documentation
- Use same API key across multiple projects
- Expose secrets in error messages

---

**Last Updated**: February 2026
