"""
Middleware para Cloud Hubs - SSO Authentication.

Este middleware solo se activa para Cloud Hubs (DEPLOYMENT_MODE='web').
Desktop Hubs siguen usando su sistema de login con PIN.

La cookie de sesión del Cloud Portal se comparte con el Hub gracias a
SESSION_COOKIE_DOMAIN configurado en Cloud (ej: '.int.erplora.com').

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
        '/health/',  # Health check endpoint
        '/static/',  # Static files
        '/media/',   # Media files
        '/favicon.ico',  # Favicon
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
        is_authenticated, user_email = self._verify_session_with_cloud(session_id)

        if not is_authenticated:
            logger.info(f"[SSO] Invalid session. Redirecting to login.")
            return self._redirect_to_login(request)

        # En modo DEMO, cualquier usuario autenticado tiene acceso
        # No verificamos permisos de Hub específico
        if self.demo_mode:
            logger.info(f"[SSO] DEMO MODE: User {user_email} authenticated - access granted")
            request.cloud_user_email = user_email
            return self.get_response(request)

        # Verificar que el usuario tiene acceso a este Hub (solo modo producción)
        has_access = self._verify_hub_access(session_id, user_email)

        if not has_access:
            logger.warning(f"[SSO] User {user_email} does not have access to Hub {self.hub_id}")
            return self._render_no_access_page(request, user_email)

        # Usuario autenticado y con acceso → permitir request
        logger.info(f"[SSO] User {user_email} authenticated and has access to Hub {self.hub_id}")
        request.cloud_user_email = user_email  # Añadir email al request para uso en views

        return self.get_response(request)

    def _is_exempt_url(self, path):
        """Verifica si la URL está exenta de autenticación."""
        for exempt_url in self.EXEMPT_URLS:
            if path.startswith(exempt_url):
                return True
        return False

    def _verify_session_with_cloud(self, session_id):
        """
        Verifica la sesión con Cloud API.

        Returns:
            tuple: (is_authenticated: bool, user_email: str or None)
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
                    return True, data.get('email')
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
        # Allauth usa /accounts/login/ no /login/
        login_url = f"{self.cloud_api_url}/accounts/login/"

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
