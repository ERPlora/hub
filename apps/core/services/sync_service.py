"""
Servicio de sincronización para operaciones offline.

Procesa la cola de sincronización y envía operaciones pendientes al Cloud.
"""
import requests
import logging
from django.conf import settings
from apps.sync.models import SyncQueue
from apps.configuration.models import HubConfig

logger = logging.getLogger(__name__)


class SyncService:
    """
    Servicio que procesa la cola de sincronización.

    Se ejecuta periódicamente para enviar operaciones pendientes al Cloud.
    """

    def __init__(self):
        self.cloud_api_url = settings.CLOUD_API_URL
        self.hub_config = HubConfig.get_config()

    def process_queue(self, batch_size=10):
        """
        Procesar cola de sincronización.

        Args:
            batch_size: Número máximo de operaciones a procesar por ejecución

        Returns:
            dict: Estadísticas de procesamiento
        """
        if not self.hub_config.is_configured:
            logger.warning("Hub not configured, skipping sync")
            return {'processed': 0, 'completed': 0, 'failed': 0}

        # Obtener operaciones pendientes
        pending_ops = SyncQueue.get_pending_operations(limit=batch_size)

        stats = {
            'processed': 0,
            'completed': 0,
            'failed': 0,
        }

        for operation in pending_ops:
            stats['processed'] += 1

            try:
                success = self._execute_operation(operation)

                if success:
                    operation.mark_completed()
                    stats['completed'] += 1
                    logger.info(f"Sync completed: {operation.operation_type} - {operation.endpoint}")
                else:
                    operation.mark_failed("Operation failed")
                    stats['failed'] += 1
                    logger.warning(f"Sync failed: {operation.operation_type} - {operation.endpoint}")

            except Exception as e:
                error_msg = f"Error executing operation: {str(e)}"
                operation.mark_failed(error_msg)
                stats['failed'] += 1
                logger.error(f"Sync error: {operation.operation_type} - {error_msg}")

        if stats['processed'] > 0:
            logger.info(f"Sync batch processed: {stats}")

        return stats

    def _execute_operation(self, operation):
        """
        Ejecutar una operación de sincronización.

        Args:
            operation: SyncQueue instance

        Returns:
            bool: True si la operación fue exitosa
        """
        # Construir URL completa
        url = f"{self.cloud_api_url}{operation.endpoint}"

        # Preparar headers
        headers = {
            'Content-Type': 'application/json',
            'X-Hub-Token': self.hub_config.tunnel_token,
            **operation.headers
        }

        try:
            # Ejecutar request según el método
            if operation.method == 'POST':
                response = requests.post(url, json=operation.payload, headers=headers, timeout=10)
            elif operation.method == 'DELETE':
                response = requests.delete(url, json=operation.payload, headers=headers, timeout=10)
            elif operation.method == 'PUT':
                response = requests.put(url, json=operation.payload, headers=headers, timeout=10)
            elif operation.method == 'PATCH':
                response = requests.patch(url, json=operation.payload, headers=headers, timeout=10)
            else:
                logger.error(f"Unsupported HTTP method: {operation.method}")
                return False

            # Verificar respuesta
            if response.status_code in [200, 201, 204]:
                return True
            else:
                logger.warning(f"Sync operation failed: {response.status_code} - {response.text}")
                return False

        except requests.exceptions.ConnectionError:
            logger.debug("No internet connection, will retry later")
            return False
        except requests.exceptions.Timeout:
            logger.warning("Request timeout, will retry later")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during sync: {str(e)}")
            raise

    def get_queue_status(self):
        """
        Obtener estado de la cola de sincronización.

        Returns:
            dict: Estado de la cola
        """
        from django.db.models import Count

        status_counts = SyncQueue.objects.values('status').annotate(count=Count('id'))

        return {
            'total': SyncQueue.objects.count(),
            'by_status': {item['status']: item['count'] for item in status_counts},
            'oldest_pending': SyncQueue.objects.filter(status='pending').order_by('created_at').first(),
        }


# Singleton instance
_sync_service = None


def get_sync_service():
    """Get or create singleton SyncService instance."""
    global _sync_service
    if _sync_service is None:
        _sync_service = SyncService()
    return _sync_service
