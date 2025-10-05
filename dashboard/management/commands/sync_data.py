from django.core.management.base import BaseCommand
from dashboard.services import DataSyncService


class Command(BaseCommand):
    help = 'Sync loan data from external API'

    def handle(self, *args, **options):
        self.stdout.write('Starting data sync...')
        
        sync_service = DataSyncService()
        synced_count = sync_service.sync_loan_data()
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully synced {synced_count} new records')
        )
