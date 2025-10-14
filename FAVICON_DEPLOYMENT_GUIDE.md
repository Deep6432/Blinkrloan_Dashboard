# Favicon Deployment Guide

## Issue
Favicon is visible in localhost but not when deployed to server.

## Root Cause
Static files (including favicon) need to be properly collected and served in production.

## Solution

### 1. Collect Static Files
Run this command before deployment:
```bash
python manage.py collectstatic --noinput
```

### 2. Verify Static Files Collection
Check that favicon files are in the `staticfiles` directory:
```bash
ls -la staticfiles/images/
```
Should show:
- favicon.ico
- favicon.png
- blinkr-logo.svg

### 3. Server Configuration

#### For Production with WhiteNoise:
The production settings already include WhiteNoise middleware:
```python
MIDDLEWARE = [
    'whitenoise.middleware.WhiteNoiseMiddleware',
    # ... other middleware
]

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
```

#### For Nginx (if using):
Add to nginx configuration:
```nginx
location /static/ {
    alias /path/to/your/project/staticfiles/;
    expires 30d;
    add_header Cache-Control "public, immutable";
}

location /favicon.ico {
    alias /path/to/your/project/staticfiles/images/favicon.ico;
    expires 30d;
    add_header Cache-Control "public, immutable";
}
```

### 4. Alternative Favicon URLs
If the issue persists, try these alternative approaches in `base.html`:

#### Option 1: Direct static URL
```html
<link rel="icon" type="image/x-icon" href="/static/images/favicon.ico">
<link rel="shortcut icon" type="image/x-icon" href="/static/images/favicon.ico">
<link rel="icon" type="image/png" href="/static/images/favicon.png">
<link rel="apple-touch-icon" href="/static/images/favicon.png">
```

#### Option 2: Absolute URLs (if using CDN)
```html
<link rel="icon" type="image/x-icon" href="{{ request.scheme }}://{{ request.get_host }}{% static 'images/favicon.ico' %}">
```

### 5. Debugging Steps

#### Check if static files are accessible:
```bash
curl -I https://your-domain.com/static/images/favicon.ico
```

#### Check browser console for 404 errors:
Open browser developer tools and check Network tab for failed favicon requests.

#### Verify Django static file serving:
```bash
python manage.py findstatic images/favicon.ico
```

### 6. Quick Fix Commands

#### For immediate deployment:
```bash
# Collect static files
python manage.py collectstatic --noinput

# Restart your web server (gunicorn, uwsgi, etc.)
sudo systemctl restart your-django-service

# Or if using Docker:
docker-compose restart web
```

### 7. Current Favicon Configuration
The favicon is currently configured in `templates/base.html`:
```html
<link rel="icon" type="image/x-icon" href="{% static 'images/favicon.ico' %}">
<link rel="shortcut icon" type="image/x-icon" href="{% static 'images/favicon.ico' %}">
<link rel="icon" type="image/png" href="{% static 'images/favicon.png' %}">
<link rel="apple-touch-icon" href="{% static 'images/favicon.png' %}">
```

### 8. Files to Check
- ✅ `/static/images/favicon.ico` - exists
- ✅ `/static/images/favicon.png` - exists  
- ✅ `/staticfiles/images/favicon.ico` - collected
- ✅ `/staticfiles/images/favicon.png` - collected
- ✅ `settings_production.py` - WhiteNoise configured
- ✅ `templates/base.html` - favicon links configured

## Most Likely Solution
Run `python manage.py collectstatic --noinput` on your production server and restart your web server.
