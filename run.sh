#!/bin/bash

# BlinkR Dashboard Setup and Run Script

echo "🚀 Setting up BlinkR Loan Dashboard..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Run migrations
echo "🗄️  Running database migrations..."
python manage.py makemigrations
python manage.py migrate

# Sync initial data
echo "🔄 Syncing initial data from API..."
python manage.py sync_data

# Start development server
echo "🌟 Starting development server..."
echo "📊 Dashboard will be available at: http://localhost:8000/"
echo "⚙️  Admin panel at: http://localhost:8000/admin/"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

python manage.py runserver
