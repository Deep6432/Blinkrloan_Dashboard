# Static Files & Favicon Deployment Checklist

## ⚠️ IMPORTANT: Run This Before Every Deployment

### Step 1: Collect Static Files (REQUIRED)
```bash
python manage.py collectstatic --noinput
```

This collects all static files (including favicon) into the `staticfiles/` directory.

### Step 2: Verify Favicon Files
```bash
ls -la staticfiles/images/
```

Should show:
- ✅ `favicon.ico`
- ✅ `favicon.png`
- ✅ `blinkr-logo.svg`

### Step 3: Restart Your Web Server

**For Gunicorn:**
```bash
sudo systemctl restart gunicorn
# or
sudo systemctl restart your-django-service
```

**For Docker:**
```bash
docker-compose restart web
```

**For AWS/Elastic Beanstalk:**
The deployment process should handle this automatically, but you may need to add a post-deploy hook.

### Step 4: Test Favicon
Open your browser and check:
- `https://your-domain.com/favicon.ico`
- `https://your-domain.com/static/images/favicon.ico`

Both should return the favicon file (not 404).

## Troubleshooting

### If favicon still doesn't show:

1. **Check Browser Cache**
   - Hard refresh: `Ctrl+Shift+R` (Windows/Linux) or `Cmd+Shift+R` (Mac)
   - Or open in incognito/private mode

2. **Check Server Logs**
   ```bash
   # Check if static files are being served
   tail -f /var/log/your-django-app.log
   ```

3. **Verify WhiteNoise is Working**
   ```bash
   curl -I https://your-domain.com/static/images/favicon.ico
   ```
   Should return `200 OK`

4. **Check File Permissions**
   ```bash
   chmod 644 staticfiles/images/favicon.ico
   chmod 644 staticfiles/images/favicon.png
   ```

5. **Manual Check**
   ```bash
   python manage.py findstatic images/favicon.ico
   ```

## Production Deployment Script

Add this to your deployment script:

```bash
#!/bin/bash
# deploy.sh

# Activate virtual environment
source venv/bin/activate

# Collect static files
python manage.py collectstatic --noinput

# Restart server (adjust based on your setup)
sudo systemctl restart your-django-service

echo "Deployment complete! Static files collected."
```

## Current Configuration

- ✅ Favicon route added: `/favicon.ico` → redirects to `/static/images/favicon.ico`
- ✅ Multiple favicon formats in `base.html` for compatibility
- ✅ WhiteNoise configured in `settings_production.py`
- ✅ STATIC_ROOT set to `staticfiles/` directory

## Files Modified

1. **`blinkr_dashboard/urls.py`**: Added direct favicon route
2. **`templates/base.html`**: Enhanced favicon links with fallbacks

