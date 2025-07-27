# Security Guidelines

## 🔐 Secrets Management

### ✅ What We've Secured:
- **Spotify API Credentials**: Moved to environment variables
- **AWS Credentials**: Protected in gitignore (commented out in config)
- **Email Passwords**: Sanitized from config files
- **Secret Keys**: Template values only in config files
- **Transcripts**: Added to gitignore (potential copyright issues)
- **Database Files**: Protected in gitignore
- **User Data**: All personal data excluded from git

### ⚠️ NEVER Commit These Files:
```
config.env                  # Contains real API keys
data/transcripts/          # Copyrighted content
data/databases/           # Personal data
saved_podcasts.json       # User's personal data
*.db                      # Database files
.spotifycache            # Spotify auth cache
```

### 🛡️ Security Checklist

#### Before Each Commit:
- [ ] Run `git status` and verify no sensitive files are staged
- [ ] Check config.env contains only template values
- [ ] Ensure no hardcoded API keys in code
- [ ] Verify .gitignore is protecting sensitive data

#### Environment Setup:
- [ ] Copy `config/env/config.env.example` to `config/env/config.env`
- [ ] Fill in your actual API keys and secrets
- [ ] Never commit the real config.env file
- [ ] Use environment variables in production

#### API Key Management:
- [ ] Spotify keys: Store in `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET`
- [ ] Rotate keys if they're ever exposed
- [ ] Use minimal scope permissions
- [ ] Monitor usage for unexpected activity

### 🔧 Secure Configuration

#### Spotify Setup:
```bash
# In config/env/config.env (NOT committed)
SPOTIFY_CLIENT_ID=your_actual_client_id
SPOTIFY_CLIENT_SECRET=your_actual_client_secret
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback/
```

#### Generate Secure Keys:
```bash
# Secret Key
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Spotify Token Encryption Key  
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 🚨 If Secrets Are Exposed:

1. **Immediately revoke/rotate** the exposed keys
2. **Remove from git history** if committed:
   ```bash
   git filter-branch --force --index-filter \
   'git rm --cached --ignore-unmatch config.env' \
   --prune-empty --tag-name-filter cat -- --all
   ```
3. **Force push** (if safe to do so)
4. **Generate new keys** and update configuration
5. **Audit access logs** for unauthorized usage

### 📁 Protected Directories

```
data/transcripts/     # Podcast transcripts (copyright)
data/databases/       # SQLite files with embeddings
data/exports/         # User's personal data
config/env/          # Environment files
.spotifycache        # Spotify authentication cache
```

### 🔍 Regular Security Audits

#### Monthly:
- [ ] Review git history for accidentally committed secrets
- [ ] Check API usage for anomalies
- [ ] Rotate long-lived tokens
- [ ] Update dependencies

#### Tools for Scanning:
```bash
# Scan for potential secrets
grep -r "api[_-]\?key\|secret\|token\|password" . --exclude-dir=node_modules

# Check what's staged for commit
git diff --cached --name-only
```

### 📞 Incident Response

If you discover exposed secrets:
1. **Stop** - Don't commit anything else
2. **Revoke** - Disable the exposed credentials immediately  
3. **Clean** - Remove from codebase and git history
4. **Replace** - Generate new credentials
5. **Report** - Document the incident and lessons learned

---

## 🛠️ Implementation Status

### ✅ Completed Security Measures:
- [x] Updated .gitignore with comprehensive sensitive data protection
- [x] Removed hardcoded Spotify credentials from code
- [x] Sanitized config.env file (template values only)
- [x] Added transcripts to gitignore
- [x] Protected all database files
- [x] Added user data protection
- [x] Created secure configuration examples

### 📋 Setup Instructions:
1. Copy `config/env/config.env.example` to `config/env/config.env`
2. Add your real API keys to the new config.env file
3. Never commit the real config.env file
4. The .gitignore will protect it automatically

**Remember: Security is everyone's responsibility!** 🔒