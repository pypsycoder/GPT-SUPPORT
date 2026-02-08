# Test Accounts and Credentials

## Quick Reference

### Researcher Account
- **Username:** `testadmin`
- **Password:** `admin123`
- **ID:** 1

### Patient Accounts

| ID | Name | Patient Number | PIN (Current) | Token |
|----|------|-----------------|---------------|-------|
| 1 | Иван Иванов | 6601 | 4626 | Oh-mYCR-f2vVWgXVXHjUwayVPYdpLGpb |
| 2 | Мария Сидорова | 1370 | 8445 | PQKuhl_qoz31nQDTA1SD9271P2jPBNLv |

## How to Use

### 1. Get Current Credentials
To see all current test accounts and their credentials:
```bash
python -m scripts.show_credentials
```

### 2. Create New Researcher
```bash
python -m scripts.create_researcher --username <username> --password <password> --name "<Full Name>"
```

Example:
```bash
python -m scripts.create_researcher --username admin2 --password secret456 --name "Dr. Петров"
```

### 3. Create New Patient
```bash
python -m scripts.create_test_user --name "<Full Name>" --age <age> --gender "<M/Ж>"
```

Example:
```bash
python -m scripts.create_test_user --name "Петр Сергеев" --age 50 --gender "М"
```

### 4. Reset All Passwords/PINs
To reset all patient PINs and see new ones:
```bash
python -m scripts.reset_all_pins
```

## Testing the Application

### Web Interface
- **URL:** http://127.0.0.1:8000/login
- **Patient Login:** Use Patient Number + PIN
- **Researcher Login:** (if available) Use username + password

### API Endpoints
- **Health Check:** http://127.0.0.1:8000/health
- **API Docs:** http://127.0.0.1:8000/docs (Swagger UI)
- **ReDoc:** http://127.0.0.1:8000/redoc

### Example Login Credentials for Testing
1. **Patient 1 (Иван Иванов):**
   - Patient Number: `6601`
   - PIN: `4626`

2. **Patient 2 (Мария Сидорова):**
   - Patient Number: `1370`
   - PIN: `8445`

## Database Status

### Current Tables
- ✅ users.users (patients)
- ✅ users.researchers
- ✅ users.sessions
- ✅ scales.scale_results
- ✅ vitals.* (4 tables)
- ✅ education.* (8 tables)

### Alembic Migration
- Current version: `5e1f8a2c3b4d`
- Status: Applied ✅

## Notes

- PIN codes are hashed in the database and cannot be recovered
- Use `scripts.reset_all_pins` to generate new PINs
- Patient tokens are auto-generated and unique
- All timestamps use UTC timezone
