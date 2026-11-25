# Application definition

INSTALLED_APPS = [
    # Before daphne: its runserver (daphne + Vite) must win.
    "live",
    "daphne",
    # The control database's registry of hubs: never inside a hub's database.
    "control",
    # Before the admin: base/templates/admin/ overrides its templates (the chosen hub's banner).
    "base",
    # The mirror of the SaaS's `shared` schema: only base/catalog.py writes it.
    "shared",
    # Django's admin, its site the Hub's own: a hub's model only once a business is chosen (base/admin_site.py).
    "base.admin_site.AdminConfig",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "ninja",
    "apps.demo",
    "apps.customer",
    "apps.staff",
    "apps.tax",
    "apps.inventory",
    "apps.sale",
    "apps.service",
    "apps.schedule",
    "apps.cash_register",
    "apps.invoice",
    "apps.appointment",
    "apps.online_booking",
    "apps.reservation",
    "apps.pricing",
    "apps.combo",
    "apps.attendance",
    "apps.table",
    "apps.kitchen",
    "apps.task",
    "apps.whatsapp_inbox",
    "apps.flow",
    "apps.verifactu",
    "apps.payment",
    "apps.printing",
    "apps.cart_checkout",
    "apps.modifier",
    "apps.website",
    "apps.tip",
]

MIDDLEWARE = [
    # First: answers /healthz before the Host is validated.
    "base.health.HealthCheckMiddleware",
    # Then: a cut of the database waits and repeats the whole request, when it may (live.database_cut, BASE-F111; Django
    # turns an exception into a response at every layer, so only the outermost sees it all).
    "live.database_cut.DatabaseCutMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # The language a person chose in this request (base.profile.preferences_set, from any door) leaves its cookie.
    "base.chosen_language.ChosenLanguageMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    # A business's own domain (HUBS-F17) answers here, before the Host is refused: only its website, by no other gate.
    "base.middleware.CustomDomainMiddleware",
    "django.middleware.common.CommonMiddleware",
    # A host that is no hub (reserved or invalid first label, live.slugs) answers 404 on hub paths.
    "base.middleware.HubHostRequiredMiddleware",
    # The rest runs in the request's database: use_hub(request.hub), the admin's chosen hub.
    "base.middleware.HubDatabaseMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # A session opened on another host (another hub's, the platform's) is no session here.
    "base.session_host.SessionHostMiddleware",
    # The platform host (hubs.localhost) is only the Hub admin for the staff.
    "base.middleware.PlatformHostMiddleware",
    # No login of its own: a browser without a session on a SPA route goes to the SaaS's login.
    "base.middleware.SaasLoginRequiredMiddleware",
    # API 404/405 that never reach a route (unknown path, wrong method) answer the JSON envelope.
    "live.api_errors.ApiErrorEnvelopeMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.csp",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                # The hub chosen for the admin (deep link /admin/hub/<slug>/), shown in its banner.
                "base.admin.admin_hub_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
