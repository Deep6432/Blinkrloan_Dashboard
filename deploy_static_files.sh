#!/bin/bash

# Deploy Static Files Script
# This script helps deploy static files including favicon

echo "🚀 Deploying Static Files..."

# Check if we're in the right directory
if [ ! -f "manage.py" ]; then
    echo "❌ Error: manage.py not found. Please run this script from the Django project root."
    exit 1
fi

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    echo "📦 Activating virtual environment..."
    source venv/bin/activate
fi

# Collect static files
echo "📁 Collecting static files..."
python manage.py collectstatic --noinput

# Check if favicon files exist
echo "🔍 Checking favicon files..."
if [ -f "staticfiles/images/favicon.ico" ]; then
    echo "✅ favicon.ico found in staticfiles"
else
    echo "❌ favicon.ico NOT found in staticfiles"
fi

if [ -f "staticfiles/images/favicon.png" ]; then
    echo "✅ favicon.png found in staticfiles"
else
    echo "❌ favicon.png NOT found in staticfiles"
fi

# Show static files size
echo "📊 Static files size:"
du -sh staticfiles/

echo ""
echo "🎉 Static files deployment complete!"
echo ""
echo "📝 Next steps:"
echo "1. Restart your web server (gunicorn, uwsgi, etc.)"
echo "2. Or if using Docker: docker-compose restart web"
echo "3. Check favicon at: https://your-domain.com/static/images/favicon.ico"
echo ""
echo "🔧 If favicon still doesn't work:"
echo "- Check nginx/apache configuration for static file serving"
echo "- Verify WhiteNoise middleware is enabled in production"
echo "- Check browser console for 404 errors"
