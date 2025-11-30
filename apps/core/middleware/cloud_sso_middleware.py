"""
Middleware para Cloud Hubs - SSO Authentication.

Este middleware solo se activa para Cloud Hubs (DEPLOYMENT_MODE='web').
Desktop Hubs siguen usando su sistema de login con PIN.

La cookie de sesión del Cloud Portal se comparte con el Hub gracias a
SESSION_COOKIE_DOMAIN configurado en Cloud (ej: '.int.erplora.com').

Flujo SSO completo:
  1. Usuario visita Hub → SSO verifica cookie de Cloud
  2. Si no autenticado → redirige a Cloud login
  3. Si autenticado → crea/actualiza LocalUser
  4. Si LocalUser sin PIN → redirige a /setup-pin/
  5. Si LocalUser con PIN → establece sesión y permite acceso

Requisitos:
  - Cloud debe tener SESSION_COOKIE_DOMAIN configurado según entorno:
    - INT: '.int.erplora.com'
    - PRE: '.pre.erplora.com'
    - PROD: '.erplora.com'
  - Hub debe estar en el mismo dominio (ej: demo.int.erplora.com)
"""
import logging
import requests
from django.shortcuts import redirect
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

logger = logging.getLogger(__name__)


class CloudSSOMiddleware:
    """
    Middleware de SSO para Cloud Hubs.

    Verifica que el usuario esté autenticado en Cloud leyendo la cookie 'sessionid'
    compartida gracias a SESSION_COOKIE_DOMAIN en Cloud.

    IMPORTANTE: Solo se activa si DEPLOYMENT_MODE='web' (Cloud Hub).
    Desktop Hubs (DEPLOYMENT_MODE='local') no usan este middleware.
    """

    # URLs que no requieren autenticación
    EXEMPT_URLS = [
        '/health/',  # Legacy health check endpoint
        '/ht/',      # django-health-check endpoint (for Cloud monitoring)
        '/static/',  # Static files
        '/media/',   # Media files
        '/favicon.ico',  # Favicon
        '/login/',   # Login page (handled by SSO)
        '/cloud-login/',  # Cloud login endpoint
        '/setup-pin/',  # PIN setup endpoint
        '/verify-pin/',  # PIN verification endpoint
        '/logout/',  # Logout endpoint
    ]

    def __init__(self, get_response):
        self.get_response = get_response
        # Use settings instead of decouple for consistency
        self.deployment_mode = getattr(settings, 'DEPLOYMENT_MODE', 'local')
        self.cloud_api_url = getattr(settings, 'CLOUD_API_URL', 'https://erplora.com')
        self.hub_id = getattr(settings, 'HUB_ID', '')
        self.demo_mode = getattr(settings, 'DEMO_MODE', False)

    def __call__(self, request):
        # Solo aplicar middleware en Cloud Hubs
        if self.deployment_mode != 'web':
            return self.get_response(request)

        # Skip URLs exentas
        if self._is_exempt_url(request.path):
            return self.get_response(request)

        # Obtener cookie de sesión
        session_id = request.COOKIES.get('sessionid')

        if not session_id:
            logger.info(f"[SSO] No sessionid cookie found. Redirecting to login.")
            return self._redirect_to_login(request)

        # Verificar sesión con Cloud API
        is_authenticated, user_data = self._verify_session_with_cloud(session_id)

        if not is_authenticated:
            logger.info(f"[SSO] Invalid session. Redirecting to login.")
            return self._redirect_to_login(request)

        user_email = user_data.get('email')

        # En modo DEMO, cualquier usuario autenticado tiene acceso
        # No verificamos permisos de Hub específico
        if self.demo_mode:
            logger.info(f"[SSO] DEMO MODE: User {user_email} authenticated - access granted")
        else:
            # Verificar que el usuario tiene acceso a este Hub (solo modo producción)
            has_access = self._verify_hub_access(session_id, user_email)

            if not has_access:
                logger.warning(f"[SSO] User {user_email} does not have access to Hub {self.hub_id}")
                return self._render_no_access_page(request, user_email)

            logger.info(f"[SSO] User {user_email} authenticated and has access to Hub {self.hub_id}")

        # Establecer datos de Cloud en request para uso en views
        request.cloud_user_email = user_email
        request.cloud_user_data = user_data

        # Verificar si el usuario ya tiene sesión local válida
        local_user_id = request.session.get('local_user_id')
        if local_user_id:
            # Ya tiene sesión local, permitir acceso
            return self.get_response(request)

        # No tiene sesión local → crear/obtener LocalUser y verificar PIN
        redirect_response = self._ensure_local_user_and_session(request, user_data)
        if redirect_response:
            return redirect_response

        return self.get_response(request)

    def _is_exempt_url(self, path):
        """Verifica si la URL está exenta de autenticación."""
        for exempt_url in self.EXEMPT_URLS:
            if path.startswith(exempt_url):
                return True
        return False

    def _ensure_local_user_and_session(self, request, user_data):
        """
        Crea o obtiene LocalUser y establece sesión.

        Si el usuario no tiene PIN configurado, redirige a /setup-pin/.
        Si tiene PIN, establece la sesión local.

        Args:
            request: Django request
            user_data: dict with 'email', 'user_id', 'name' from Cloud API

        Returns:
            HttpResponse redirect si necesita configurar PIN, None si sesión establecida
        """
        from apps.accounts.models import LocalUser
        from apps.configuration.models import HubConfig

        user_email = user_data.get('email')
        cloud_user_id = user_data.get('user_id')
        cloud_name = user_data.get('name', '')

        try:
            # Intentar obtener usuario existente
            local_user = LocalUser.objects.filter(email=user_email).first()

            if not local_user:
                # Crear nuevo usuario
                hub_config = HubConfig.get_config()
                is_first_user = LocalUser.objects.count() == 0

                # Use name from Cloud if available, otherwise extract from email
                name = cloud_name if cloud_name else user_email.split('@')[0]

                local_user = LocalUser.objects.create(
                    cloud_user_id=cloud_user_id,  # Link to Cloud user (nullable)
                    email=user_email,
                    name=name,
                    role='admin' if is_first_user else 'cashier',
                    pin_hash='',  # Sin PIN todavía
                    language=hub_config.os_language,
                )
                logger.info(f"[SSO] Created LocalUser for {user_email}")

            # Si usuario estaba inactivo, reactivarlo
            if not local_user.is_active:
                local_user.is_active = True
                local_user.pin_hash = ''  # Reset PIN
                local_user.save(update_fields=['is_active', 'pin_hash'])
                logger.info(f"[SSO] Reactivated LocalUser for {user_email}")

            # Verificar si tiene PIN configurado
            if not local_user.pin_hash:
                # Guardar user_id en sesión temporalmente para setup-pin
                request.session['pending_user_id'] = local_user.id
                request.session['pending_user_email'] = user_email
                logger.info(f"[SSO] User {user_email} needs to setup PIN, redirecting...")
                return redirect('/setup-pin/')

            # Usuario tiene PIN → establecer sesión completa
            local_user.last_login = timezone.now()
            local_user.save(update_fields=['last_login'])

            request.session['local_user_id'] = local_user.id
            request.session['user_name'] = local_user.name
            request.session['user_email'] = local_user.email
            request.session['user_role'] = local_user.role
            request.session['user_language'] = local_user.language

            logger.info(f"[SSO] Session established for {user_email}")
            return None

        except Exception as e:
            logger.error(f"[SSO] Error ensuring local user: {str(e)}")
            # En caso de error, permitir que continúe (fallback)
            return None

    def _verify_session_with_cloud(self, session_id):
        """
        Verifica la sesión con Cloud API.

        Returns:
            tuple: (is_authenticated: bool, user_data: dict or None)
                   user_data contains: email, user_id, name
        """
        try:
            response = requests.get(
                f"{self.cloud_api_url}/api/auth/verify-session/",
                cookies={'sessionid': session_id},
                timeout=5
            )

            if response.status_code == 200:
                data = response.json()
                # Cloud returns 'authenticated' field, check it
                if data.get('authenticated'):
                    return True, {
                        'email': data.get('email'),
                        'user_id': data.get('user_id'),
                        'name': data.get('name', ''),
                    }
                else:
                    return False, None
            else:
                logger.warning(f"[SSO] Session verification failed: {response.status_code}")
                return False, None

        except requests.exceptions.RequestException as e:
            logger.error(f"[SSO] Error verifying session with Cloud: {str(e)}")
            # En caso de error de red, denegar acceso por seguridad
            # El usuario será redirigido al login
            return False, None

    def _verify_hub_access(self, session_id, user_email):
        """
        Verifica que el usuario tiene acceso a este Hub específico.

        Returns:
            bool: True si tiene acceso, False si no
        """
        if not self.hub_id:
            logger.warning("[SSO] HUB_ID not configured, allowing access")
            return True

        try:
            response = requests.get(
                f"{self.cloud_api_url}/api/hubs/{self.hub_id}/check-access/",
                cookies={'sessionid': session_id},
                timeout=5
            )

            if response.status_code == 200:
                data = response.json()
                return data.get('has_access', False)
            else:
                logger.warning(f"[SSO] Hub access check failed: {response.status_code}")
                # En caso de error, denegar acceso por seguridad
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"[SSO] Error checking Hub access: {str(e)}")
            # En caso de error de red, permitir acceso (fallback)
            return True

    def _redirect_to_login(self, request):
        """Redirige al login de Cloud con next parameter."""
        # two_factor usa /account/login/ (sin 's')
        # /accounts/login/ redirige a /account/login/
        login_url = f"{self.cloud_api_url}/account/login/"

        # Construir next_url asegurando HTTPS en producción
        next_url = request.build_absolute_uri()
        # Forzar HTTPS si estamos en modo web (no local)
        if self.deployment_mode == 'web' and next_url.startswith('http://'):
            next_url = next_url.replace('http://', 'https://', 1)

        redirect_url = f"{login_url}?next={next_url}"

        logger.info(f"[SSO] Redirecting to login: {redirect_url}")
        return redirect(redirect_url)

    def _render_no_access_page(self, request, user_email):
        """Renderiza página de sin acceso (403)."""
        from django.http import HttpResponse

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Access Denied</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                }}
                .container {{
                    background: white;
                    padding: 3rem;
                    border-radius: 12px;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                    text-align: center;
                    max-width: 500px;
                }}
                h1 {{
                    color: #e53e3e;
                    margin-bottom: 1rem;
                    font-size: 2rem;
                }}
                p {{
                    color: #4a5568;
                    margin-bottom: 1.5rem;
                    line-height: 1.6;
                }}
                .email {{
                    color: #667eea;
                    font-weight: 600;
                }}
                .hub-id {{
                    color: #764ba2;
                    font-weight: 600;
                }}
                a {{
                    display: inline-block;
                    background: #667eea;
                    color: white;
                    padding: 0.75rem 2rem;
                    border-radius: 6px;
                    text-decoration: none;
                    font-weight: 600;
                    transition: background 0.2s;
                }}
                a:hover {{
                    background: #5a67d8;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🔒 Access Denied</h1>
                <p>
                    User <span class="email">{user_email or 'Unknown'}</span>
                    does not have access to Hub <span class="hub-id">{self.hub_id}</span>.
                </p>
                <p>
                    Please contact the Hub owner to request access.
                </p>
                <a href="{self.cloud_api_url}/dashboard/">Go to Dashboard</a>
            </div>
        </body>
        </html>
        """

        return HttpResponse(html, status=403)
