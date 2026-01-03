"""
Database and filesystem maintenance views for orphaned module data
"""
import json
import shutil
import sqlite3
from pathlib import Path
from django.http import JsonResponse, HttpResponse
from django.conf import settings as django_settings
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.template.loader import render_to_string
from django.urls import reverse
from djicons import icon as render_icon


def scan_orphaned_data(request):
    """
    Scan for orphaned database tables and media files from deleted modules
    """
    # Check if user is logged in
    if 'local_user_id' not in request.session:
        alert_icon = render_icon("alert-circle-outline", css_class="text-2xl text-danger")
        html = f'''
            <ion-card class="border-l-4 border-danger">
                <ion-card-content class="flex items-center gap-3">
                    {alert_icon}
                    <ion-label class="text-danger">Not authenticated</ion-label>
                </ion-card-content>
            </ion-card>
        '''
        return HttpResponse(html, status=401)

    try:
        from config.paths import get_database_path, get_media_dir

        # Get active modules from filesystem
        modules_dir = Path(django_settings.MODULES_DIR)
        active_modules = set()

        if modules_dir.exists():
            for module_dir in modules_dir.iterdir():
                if module_dir.is_dir() and not module_dir.name.startswith('_') and not module_dir.name.startswith('.'):
                    active_modules.add(module_dir.name)

        # Connect to database
        db_path = get_database_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Find orphaned tables (tables that don't belong to active modules or Django)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        all_tables = [row[0] for row in cursor.fetchall()]

        # Django core tables (whitelist)
        django_tables = {
            'django_migrations', 'django_session', 'django_content_type',
            'django_admin_log', 'auth_permission', 'auth_group',
            'auth_group_permissions', 'auth_user', 'auth_user_groups',
            'auth_user_user_permissions', 'sqlite_sequence'
        }

        # Core app tables (whitelist)
        core_app_prefixes = [
            'configuration_',  # apps.configuration
            'accounts_',       # apps.accounts
            'sync_',          # apps.sync
            'modules_admin_', # apps.modules_admin
            'core_',          # Legacy core app tables (before refactoring)
        ]

        orphaned_tables = []
        for table in all_tables:
            # Skip Django tables
            if table in django_tables:
                continue

            # Skip core app tables
            is_core = False
            for prefix in core_app_prefixes:
                if table.startswith(prefix):
                    is_core = True
                    break
            if is_core:
                continue

            # Check if table belongs to an active module
            table_module = None
            for module in active_modules:
                if table.startswith(f'{module}_'):
                    table_module = module
                    break

            if not table_module:
                orphaned_tables.append(table)

        # Find orphaned migrations (if table exists)
        orphaned_migrations = []
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='django_migrations'")
        if cursor.fetchone():
            cursor.execute("SELECT app, name FROM django_migrations ORDER BY app, name")
            all_migrations = cursor.fetchall()

            # Core apps (whitelist)
            core_apps = {
                'configuration', 'accounts', 'sync', 'modules_admin',
                'contenttypes', 'auth', 'sessions', 'admin',
                'core', 'modules'  # Legacy apps (before refactoring)
            }

            for app, name in all_migrations:
                if app in core_apps:
                    continue
                if app not in active_modules:
                    orphaned_migrations.append({'app': app, 'name': name})

        conn.close()

        # Find orphaned media folders
        media_dir = get_media_dir()
        orphaned_media = []

        if media_dir.exists():
            for folder in media_dir.iterdir():
                if folder.is_dir() and folder.name not in active_modules:
                    # Skip common media folders
                    if folder.name in ['avatars', 'uploads', 'temp', 'products']:
                        continue
                    orphaned_media.append(folder.name)

        # Return HTML for HTMX
        total_orphans = len(orphaned_tables) + len(orphaned_migrations) + len(orphaned_media)

        if total_orphans == 0:
            success_icon = render_icon("checkmark-circle-outline", css_class="text-2xl text-success")
            html = f'''
                <ion-card class="border-l-4 border-success">
                    <ion-card-content class="flex items-center gap-3">
                        {success_icon}
                        <ion-label class="text-success">
                            No orphaned data found
                        </ion-label>
                    </ion-card-content>
                </ion-card>
            '''
        else:
            clean_url = reverse('configuration:clean_orphaned_data')
            items = []
            if orphaned_tables:
                items.append(f'<li>{len(orphaned_tables)} orphaned database tables</li>')
            if orphaned_migrations:
                items.append(f'<li>{len(orphaned_migrations)} orphaned migration records</li>')
            if orphaned_media:
                items.append(f'<li>{len(orphaned_media)} orphaned media folders</li>')

            trash_icon = render_icon("trash-outline", slot="start")
            html = f'''
                <ion-card class="border-l-4 border-warning">
                    <ion-card-content>
                        <ion-label class="font-semibold text-warning block mb-2">
                            Orphaned Data Found:
                        </ion-label>
                        <ul class="m-0 pl-5 text-medium text-sm">
                            {''.join(items)}
                        </ul>
                        <ion-button
                            color="danger"
                            size="small"
                            hx-post="{clean_url}"
                            hx-target="#scan-results"
                            class="mt-3">
                            {trash_icon}
                            Clean Orphaned Data
                        </ion-button>
                    </ion-card-content>
                </ion-card>
            '''

        return HttpResponse(html)

    except Exception as e:
        alert_icon = render_icon("alert-circle-outline", css_class="text-2xl text-danger")
        html = f'''
            <ion-card class="border-l-4 border-danger">
                <ion-card-content class="flex items-center gap-3">
                    {alert_icon}
                    <ion-label class="text-danger">Error: {str(e)}</ion-label>
                </ion-card-content>
            </ion-card>
        '''
        return HttpResponse(html, status=500)


def clean_orphaned_data(request):
    """
    Clean orphaned database tables and media files from deleted modules
    """
    # Only allow POST
    if request.method != 'POST':
        alert_icon = render_icon("alert-circle-outline", css_class="text-2xl text-danger")
        html = f'''
            <ion-card class="border-l-4 border-danger">
                <ion-card-content class="flex items-center gap-3">
                    {alert_icon}
                    <ion-label class="text-danger">Method not allowed</ion-label>
                </ion-card-content>
            </ion-card>
        '''
        return HttpResponse(html, status=405)

    # Check if user is logged in
    if 'local_user_id' not in request.session:
        alert_icon = render_icon("alert-circle-outline", css_class="text-2xl text-danger")
        html = f'''
            <ion-card class="border-l-4 border-danger">
                <ion-card-content class="flex items-center gap-3">
                    {alert_icon}
                    <ion-label class="text-danger">Not authenticated</ion-label>
                </ion-card-content>
            </ion-card>
        '''
        return HttpResponse(html, status=401)

    try:
        from config.paths import get_database_path, get_media_dir

        # Get active modules from filesystem
        modules_dir = Path(django_settings.MODULES_DIR)
        active_modules = set()

        if modules_dir.exists():
            for module_dir in modules_dir.iterdir():
                if module_dir.is_dir() and not module_dir.name.startswith('_') and not module_dir.name.startswith('.'):
                    active_modules.add(module_dir.name)

        # Connect to database
        db_path = get_database_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Find orphaned tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        all_tables = [row[0] for row in cursor.fetchall()]

        # Django core tables (whitelist)
        django_tables = {
            'django_migrations', 'django_session', 'django_content_type',
            'django_admin_log', 'auth_permission', 'auth_group',
            'auth_group_permissions', 'auth_user', 'auth_user_groups',
            'auth_user_user_permissions', 'sqlite_sequence'
        }

        # Core app tables (whitelist)
        core_app_prefixes = [
            'configuration_',  # apps.configuration
            'accounts_',       # apps.accounts
            'sync_',          # apps.sync
            'modules_admin_', # apps.modules_admin
            'core_',          # Legacy core app tables (before refactoring)
        ]

        orphaned_tables = []
        for table in all_tables:
            # Skip Django tables
            if table in django_tables:
                continue

            # Skip core app tables
            is_core = False
            for prefix in core_app_prefixes:
                if table.startswith(prefix):
                    is_core = True
                    break
            if is_core:
                continue

            # Check if table belongs to an active module
            table_module = None
            for module in active_modules:
                if table.startswith(f'{module}_'):
                    table_module = module
                    break

            if not table_module:
                orphaned_tables.append(table)

        # Find orphaned migrations (if table exists)
        orphaned_migrations = []
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='django_migrations'")
        if cursor.fetchone():
            cursor.execute("SELECT app, name FROM django_migrations ORDER BY app, name")
            all_migrations = cursor.fetchall()

            # Core apps (whitelist)
            core_apps = {
                'configuration', 'accounts', 'sync', 'modules_admin',
                'contenttypes', 'auth', 'sessions', 'admin',
                'core', 'modules'  # Legacy apps (before refactoring)
            }

            for app, name in all_migrations:
                if app in core_apps:
                    continue
                if app not in active_modules:
                    orphaned_migrations.append({'app': app, 'name': name})

        # Delete orphaned tables
        for table in orphaned_tables:
            try:
                cursor.execute(f'DROP TABLE IF EXISTS {table}')
            except Exception as e:
                print(f'[CLEAN] Error dropping table {table}: {e}')

        # Delete orphaned migrations
        for migration in orphaned_migrations:
            try:
                cursor.execute(
                    'DELETE FROM django_migrations WHERE app = ? AND name = ?',
                    (migration['app'], migration['name'])
                )
            except Exception as e:
                print(f'[CLEAN] Error deleting migration {migration}: {e}')

        conn.commit()
        conn.close()

        # Find and delete orphaned media folders
        media_dir = get_media_dir()
        orphaned_media = []

        if media_dir.exists():
            for folder in media_dir.iterdir():
                if folder.is_dir() and folder.name not in active_modules:
                    # Skip common media folders
                    if folder.name in ['avatars', 'uploads', 'temp', 'products']:
                        continue
                    orphaned_media.append(folder.name)

        for folder_name in orphaned_media:
            folder_path = media_dir / folder_name
            if folder_path.exists() and folder_path.is_dir():
                try:
                    shutil.rmtree(folder_path)
                except Exception as e:
                    print(f'[CLEAN] Error deleting media folder {folder_name}: {e}')

        total_cleaned = len(orphaned_tables) + len(orphaned_migrations) + len(orphaned_media)

        # Return HTML for HTMX
        success_icon = render_icon("checkmark-circle-outline", css_class="text-2xl text-success")
        html = f'''
            <ion-card class="border-l-4 border-success">
                <ion-card-content>
                    <div class="flex items-center gap-3 mb-2">
                        {success_icon}
                        <ion-label class="font-semibold text-success">
                            Successfully cleaned {total_cleaned} orphaned items
                        </ion-label>
                    </div>
                    <ul class="m-0 pl-5 text-medium text-sm">
                        <li>{len(orphaned_tables)} database tables deleted</li>
                        <li>{len(orphaned_migrations)} migration records deleted</li>
                        <li>{len(orphaned_media)} media folders deleted</li>
                    </ul>
                </ion-card-content>
            </ion-card>
        '''

        return HttpResponse(html)

    except Exception as e:
        alert_icon = render_icon("alert-circle-outline", css_class="text-2xl text-danger")
        html = f'''
            <ion-card class="border-l-4 border-danger">
                <ion-card-content class="flex items-center gap-3">
                    {alert_icon}
                    <ion-label class="text-danger">Error: {str(e)}</ion-label>
                </ion-card-content>
            </ion-card>
        '''
        return HttpResponse(html, status=500)
