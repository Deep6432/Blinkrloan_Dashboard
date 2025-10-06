# BlinkR Loan Dashboard

A modern, responsive Django web dashboard for BlinkR Loan portfolio management with a corporate fintech aesthetic.

## Features

- **Modern UI**: Dark theme with TailwindCSS styling
- **Real-time Data**: Fetches data from BlinkR API with fallback to mock data
- **Interactive Filters**: Date range, status, DPD bucket, state, and city filters
- **KPI Cards**: Comprehensive metrics including collection rates and pending amounts
- **Data Visualization**: Chart.js powered charts for state-wise and time-series data
- **DPD Analysis**: Detailed DPD bucket distribution table
- **Responsive Design**: Works on desktop, tablet, and mobile devices

## Tech Stack

- **Backend**: Django 4.2.7
- **Frontend**: HTML5, TailwindCSS, Alpine.js, Chart.js
- **Database**: SQLite (configurable)
- **API Integration**: External BlinkR API with mock data fallback

## Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd blinkr-dashboard
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run migrations**
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   ```

5. **Create superuser (optional)**
   ```bash
   python manage.py createsuperuser
   ```

6. **Sync initial data**
   ```bash
   python manage.py sync_data
   ```

7. **Run development server**
   ```bash
   python manage.py runserver
   ```

8. **Access the dashboard**
   - Dashboard: http://localhost:8000/
   - Admin panel: http://localhost:8000/admin/

## API Endpoints

- `GET /` - Main dashboard
- `GET /api/dpd-buckets/` - DPD bucket distribution data
- `GET /api/state-repayment/` - State-wise repayment data
- `GET /api/time-series/` - Time series data
- `POST /api/sync-data/` - Manual data sync

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```env
SECRET_KEY=your-secret-key-here
DEBUG=True
EXTERNAL_API_URL=https://backend.blinkrloan.com/insights/v1/portfolio-collection-with-fraud
```

### Database Configuration

The default configuration uses SQLite. To use PostgreSQL or MySQL, update `settings.py`:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'blinkr_dashboard',
        'USER': 'your_username',
        'PASSWORD': 'your_password',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

## Usage

### Dashboard Features

1. **Filters Panel**
   - Date range selection
   - Closing status filter (Active/Closed)
   - DPD bucket filter (0-30, 31-60, 61-90, 90+)
   - State and city filters

2. **KPI Cards**
   - Total Applications
   - Sanction Amount
   - Disbursed Amount
   - Repayment Amount
   - Actual Repayment Amount
   - Repayment with Penalty
   - Earning
   - Penalty
   - Collected Amount (with percentage)
   - Pending Collection (with percentage)

3. **Charts**
   - State-wise repayment bar chart
   - Time series line chart showing repayment, collection, and percentage trends

4. **DPD Bucket Table**
   - Distribution of loans by DPD buckets
   - Visual progress bars
   - Count and percentage metrics

### Data Sync

The dashboard automatically syncs data from the external API when accessed. You can also manually sync data using:

```bash
python manage.py sync_data
```

Or via the API endpoint:
```bash
curl -X POST http://localhost:8000/api/sync-data/
```

## Deployment

### Production Settings

1. **Update settings.py**
   ```python
   DEBUG = False
   ALLOWED_HOSTS = ['your-domain.com']
   SECRET_KEY = 'your-production-secret-key'
   ```

2. **Static files**
   ```bash
   python manage.py collectstatic
   ```

3. **Use a production WSGI server**
   ```bash
   gunicorn blinkr_dashboard.wsgi:application
   ```

### Docker Deployment

Create a `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN python manage.py collectstatic --noinput
RUN python manage.py migrate

EXPOSE 8000
CMD ["gunicorn", "blinkr_dashboard.wsgi:application", "--bind", "0.0.0.0:8000"]
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License.

## Support

For support and questions, please contact the development team or create an issue in the repository.
