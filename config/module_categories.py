"""
Module Categories and Industries Configuration

Defines all available categories and industries for ERPlora modules.
This file is shared between Cloud (marketplace) and Hub (module management).

Classification System (3 levels):
1. FUNCTIONS (multiple) - Functional areas (what the module does: POS, HR, CRM, etc.)
2. INDUSTRIES (multiple) - Business verticals (who uses it)
3. TAGS (multiple) - Free keywords for search

Based on: hub/modules/MODULE_CATALOG.md
"""

# =============================================================================
# CATEGORIES - Functional categories (what the module does)
# =============================================================================

MODULE_CATEGORIES = {
    # Core Operations
    'pos': {
        'name': 'Point of Sale',
        'name_es': 'Punto de Venta',
        'description': 'Sales terminals, checkout, payments, receipts',
        'description_es': 'Terminales de venta, cobro, pagos, tickets',
        'icon': 'cash-outline',
        'order': 1,
        'color': '#3880ff',  # primary
    },
    'horeca': {
        'name': 'Hospitality',
        'name_es': 'Hostelería',
        'description': 'Tables, kitchen display, orders, reservations for hospitality',
        'description_es': 'Mesas, comandas, cocina, reservas para hostelería',
        'icon': 'restaurant-outline',
        'order': 2,
        'color': '#ff6b35',
    },
    'sales': {
        'name': 'Sales & Commerce',
        'name_es': 'Ventas y Comercio',
        'description': 'Quotations, orders, invoicing, returns, commissions',
        'description_es': 'Cotizaciones, pedidos, facturación, devoluciones, comisiones',
        'icon': 'trending-up-outline',
        'order': 3,
        'color': '#5260ff',
    },
    'inventory': {
        'name': 'Inventory & Stock',
        'name_es': 'Inventario y Stock',
        'description': 'Products, stock levels, warehouses, transfers',
        'description_es': 'Productos, niveles de stock, almacenes, transferencias',
        'icon': 'cube-outline',
        'order': 4,
        'color': '#3dc2ff',  # secondary
    },
    'purchasing': {
        'name': 'Purchasing',
        'name_es': 'Compras',
        'description': 'Purchase orders, suppliers, procurement',
        'description_es': 'Órdenes de compra, proveedores, aprovisionamiento',
        'icon': 'cart-outline',
        'order': 5,
        'color': '#5260ff',
    },
    'accounting': {
        'name': 'Accounting & Finance',
        'name_es': 'Contabilidad y Finanzas',
        'description': 'Invoicing, payments, ledger, reconciliation',
        'description_es': 'Facturación, pagos, libro mayor, conciliación',
        'icon': 'calculator-outline',
        'order': 6,
        'color': '#2dd36f',  # success
    },

    # Production
    'manufacturing': {
        'name': 'Manufacturing',
        'name_es': 'Manufactura',
        'description': 'Production planning, MRP, work orders, BOM',
        'description_es': 'Planificación de producción, MRP, órdenes de trabajo, BOM',
        'icon': 'construct-outline',
        'order': 10,
        'color': '#ffc409',  # warning
    },
    'quality': {
        'name': 'Quality Control',
        'name_es': 'Control de Calidad',
        'description': 'Inspections, certifications, compliance checks',
        'description_es': 'Inspecciones, certificaciones, controles de cumplimiento',
        'icon': 'checkmark-circle-outline',
        'order': 11,
        'color': '#2dd36f',
    },
    'maintenance': {
        'name': 'Maintenance',
        'name_es': 'Mantenimiento',
        'description': 'Asset maintenance, preventive maintenance, repairs',
        'description_es': 'Mantenimiento de activos, mantenimiento preventivo, reparaciones',
        'icon': 'build-outline',
        'order': 12,
        'color': '#ffc409',
    },

    # Customer Management
    'crm': {
        'name': 'Customers & CRM',
        'name_es': 'Clientes y CRM',
        'description': 'Customer management, loyalty, leads, opportunities',
        'description_es': 'Gestión de clientes, fidelización, prospectos, oportunidades',
        'icon': 'people-outline',
        'order': 20,
        'color': '#eb445a',  # danger
    },
    'marketing': {
        'name': 'Marketing',
        'name_es': 'Marketing',
        'description': 'Campaigns, promotions, email marketing, social media',
        'description_es': 'Campañas, promociones, email marketing, redes sociales',
        'icon': 'megaphone-outline',
        'order': 21,
        'color': '#eb445a',
    },
    'ecommerce': {
        'name': 'E-Commerce',
        'name_es': 'Comercio Electrónico',
        'description': 'Online store, shopping cart, payment gateways',
        'description_es': 'Tienda online, carrito de compra, pasarelas de pago',
        'icon': 'storefront-outline',
        'order': 22,
        'color': '#3880ff',
    },

    # Human Resources
    'hr': {
        'name': 'Human Resources',
        'name_es': 'Recursos Humanos',
        'description': 'Employees, schedules, payroll, attendance, recruitment',
        'description_es': 'Empleados, horarios, nómina, asistencia, reclutamiento',
        'icon': 'person-outline',
        'order': 30,
        'color': '#5260ff',
    },

    # Analytics (unified from reporting + analytics)
    'analytics': {
        'name': 'Reports & Analytics',
        'name_es': 'Reportes y Análisis',
        'description': 'Dashboards, reports, KPIs, business intelligence',
        'description_es': 'Tableros, reportes, KPIs, inteligencia de negocios',
        'icon': 'bar-chart-outline',
        'order': 40,
        'color': '#3dc2ff',
    },

    # Collaboration
    'project': {
        'name': 'Projects & Tasks',
        'name_es': 'Proyectos y Tareas',
        'description': 'Project management, tasks, time tracking',
        'description_es': 'Gestión de proyectos, tareas, seguimiento de tiempo',
        'icon': 'git-branch-outline',
        'order': 50,
        'color': '#92949c',  # medium
    },
    'documents': {
        'name': 'Documents',
        'name_es': 'Documentos',
        'description': 'Document management, templates, digital signatures',
        'description_es': 'Gestión de documentos, plantillas, firmas digitales',
        'icon': 'document-text-outline',
        'order': 51,
        'color': '#92949c',
    },
    'website': {
        'name': 'Website',
        'name_es': 'Sitio Web',
        'description': 'Website builder, CMS, landing pages, booking pages',
        'description_es': 'Constructor de sitios web, CMS, páginas de aterrizaje',
        'icon': 'globe-outline',
        'order': 52,
        'color': '#3880ff',
    },

    # Technical
    'integration': {
        'name': 'Integrations',
        'name_es': 'Integraciones',
        'description': 'Third-party integrations, APIs, webhooks, sync',
        'description_es': 'Integraciones con terceros, APIs, webhooks, sincronización',
        'icon': 'swap-horizontal-outline',
        'order': 60,
        'color': '#92949c',
    },
    'localization': {
        'name': 'Localization & Compliance',
        'name_es': 'Localización y Cumplimiento',
        'description': 'Country-specific features, tax regulations, legal compliance',
        'description_es': 'Funcionalidades por país, regulaciones fiscales, cumplimiento legal',
        'icon': 'shield-checkmark-outline',
        'order': 61,
        'color': '#ffc409',
    },
    'utilities': {
        'name': 'Utilities',
        'name_es': 'Utilidades',
        'description': 'Tools, helpers, import/export, backups',
        'description_es': 'Herramientas, ayudantes, importación/exportación, backups',
        'icon': 'settings-outline',
        'order': 62,
        'color': '#92949c',
    },
}

# Categories that were removed/merged (for backwards compatibility)
DEPRECATED_CATEGORIES = {
    'legal': 'localization',      # Merged into localization
    'reporting': 'analytics',     # Merged into analytics
    'recruitment': 'hr',          # Merged into hr
}

# =============================================================================
# INDUSTRIES - Business verticals (who uses the module)
# =============================================================================

MODULE_INDUSTRIES = {
    # -------------------------------------------------------------------------
    # Retail & Commerce
    # -------------------------------------------------------------------------
    'retail': {
        'name': 'Retail',
        'name_es': 'Comercio Minorista',
        'description': 'Retail stores, shops, boutiques',
        'description_es': 'Tiendas minoristas, comercios, boutiques',
        'icon': 'storefront-outline',
        'order': 1,
        'color': '#3880ff',
        'aliases': ['tienda', 'comercio', 'shop', 'store', 'boutique'],
    },
    'grocery': {
        'name': 'Grocery & Supermarket',
        'name_es': 'Alimentación y Supermercados',
        'description': 'Supermarkets, grocery stores, convenience stores',
        'description_es': 'Supermercados, tiendas de alimentación, ultramarinos',
        'icon': 'basket-outline',
        'order': 2,
        'color': '#2dd36f',
        'aliases': ['supermercado', 'alimentacion', 'ultramarinos', 'fruteria', 'supermarket', 'minimarket'],
    },
    'wholesale': {
        'name': 'Wholesale & Distribution',
        'name_es': 'Mayorista y Distribución',
        'description': 'Wholesale distributors, B2B sales, cash & carry',
        'description_es': 'Distribuidores mayoristas, ventas B2B, cash & carry',
        'icon': 'business-outline',
        'order': 3,
        'color': '#5260ff',
        'aliases': ['mayorista', 'distribuidor', 'b2b', 'cash carry'],
    },
    'ecommerce': {
        'name': 'E-Commerce',
        'name_es': 'Comercio Electrónico',
        'description': 'Online stores, digital commerce, marketplaces',
        'description_es': 'Tiendas online, comercio digital, marketplaces',
        'icon': 'globe-outline',
        'order': 4,
        'color': '#3dc2ff',
        'aliases': ['online', 'tienda online', 'web', 'marketplace'],
    },

    # -------------------------------------------------------------------------
    # Specialized Retail
    # -------------------------------------------------------------------------
    'pharmacy': {
        'name': 'Pharmacy',
        'name_es': 'Farmacia',
        'description': 'Pharmacies, drugstores, parapharmacies',
        'description_es': 'Farmacias, parafarmacias, droguerías',
        'icon': 'medkit-outline',
        'order': 10,
        'color': '#2dd36f',
        'aliases': ['farmacia', 'parafarmacia', 'drogueria', 'drugstore'],
    },
    'optics': {
        'name': 'Optics',
        'name_es': 'Óptica',
        'description': 'Optical stores, eyewear, optometry',
        'description_es': 'Ópticas, gafas, optometría',
        'icon': 'eye-outline',
        'order': 11,
        'color': '#3880ff',
        'aliases': ['optica', 'gafas', 'lentes', 'optometria', 'eyewear'],
    },
    'tobacco': {
        'name': 'Tobacco Shop',
        'name_es': 'Estanco',
        'description': 'Tobacco shops, lottery, stamps',
        'description_es': 'Estancos, loterías, sellos',
        'icon': 'pricetag-outline',
        'order': 12,
        'color': '#92949c',
        'aliases': ['estanco', 'tabaco', 'loteria'],
    },
    'florist': {
        'name': 'Florist',
        'name_es': 'Floristería',
        'description': 'Flower shops, garden centers, plant nurseries',
        'description_es': 'Floristerías, centros de jardinería, viveros',
        'icon': 'flower-outline',
        'order': 13,
        'color': '#f472b6',
        'aliases': ['floristeria', 'flores', 'jardineria', 'vivero', 'garden'],
    },
    'jewelry': {
        'name': 'Jewelry',
        'name_es': 'Joyería',
        'description': 'Jewelry stores, watches, accessories',
        'description_es': 'Joyerías, relojerías, accesorios',
        'icon': 'diamond-outline',
        'order': 14,
        'color': '#ffc409',
        'aliases': ['joyeria', 'relojeria', 'bisuteria', 'jeweler'],
    },

    # -------------------------------------------------------------------------
    # Food & Hospitality (HoReCa)
    # -------------------------------------------------------------------------
    'restaurant': {
        'name': 'Restaurants',
        'name_es': 'Restaurantes',
        'description': 'Full-service restaurants, dining establishments',
        'description_es': 'Restaurantes de servicio completo',
        'icon': 'restaurant-outline',
        'order': 20,
        'color': '#ff6b35',
        'aliases': ['restaurante', 'comedor', 'asador', 'dining'],
    },
    'bar': {
        'name': 'Bars & Pubs',
        'name_es': 'Bares y Pubs',
        'description': 'Bars, pubs, nightclubs, lounges, cocktail bars',
        'description_es': 'Bares, pubs, discotecas, lounges, coctelerías',
        'icon': 'wine-outline',
        'order': 21,
        'color': '#eb445a',
        'aliases': ['bar', 'pub', 'discoteca', 'cocteleria', 'nightclub', 'lounge'],
    },
    'cafe': {
        'name': 'Cafés & Bakeries',
        'name_es': 'Cafeterías y Panaderías',
        'description': 'Coffee shops, bakeries, pastry shops, tea houses',
        'description_es': 'Cafeterías, panaderías, pastelerías, teterías',
        'icon': 'cafe-outline',
        'order': 22,
        'color': '#92400e',
        'aliases': ['cafeteria', 'panaderia', 'pasteleria', 'teteria', 'coffee', 'bakery'],
    },
    'fast_food': {
        'name': 'Fast Food & QSR',
        'name_es': 'Comida Rápida',
        'description': 'Fast food, quick service, food trucks, takeaway',
        'description_es': 'Comida rápida, servicio rápido, food trucks, para llevar',
        'icon': 'fast-food-outline',
        'order': 23,
        'color': '#ffc409',
        'aliases': ['comida rapida', 'fast food', 'food truck', 'takeaway', 'para llevar', 'qsr'],
    },
    'hotel': {
        'name': 'Hotels & Lodging',
        'name_es': 'Hoteles y Alojamiento',
        'description': 'Hotels, hostels, B&Bs, vacation rentals, apartments',
        'description_es': 'Hoteles, hostales, B&Bs, alquileres vacacionales, apartamentos',
        'icon': 'bed-outline',
        'order': 24,
        'color': '#6366f1',
        'aliases': ['hotel', 'hostal', 'alojamiento', 'apartamento', 'lodging', 'bnb'],
    },
    'catering': {
        'name': 'Catering & Events',
        'name_es': 'Catering y Eventos',
        'description': 'Catering services, event planning, banquets',
        'description_es': 'Servicios de catering, planificación de eventos, banquetes',
        'icon': 'people-outline',
        'order': 25,
        'color': '#ec4899',
        'aliases': ['catering', 'eventos', 'banquetes', 'bodas', 'events'],
    },

    # -------------------------------------------------------------------------
    # Personal Services
    # -------------------------------------------------------------------------
    'beauty': {
        'name': 'Beauty & Wellness',
        'name_es': 'Belleza y Bienestar',
        'description': 'Hair salons, spas, nail salons, beauty centers',
        'description_es': 'Peluquerías, spas, salones de uñas, centros de belleza',
        'icon': 'cut-outline',
        'order': 30,
        'color': '#f472b6',
        'aliases': ['peluqueria', 'salon', 'spa', 'estetica', 'unas', 'belleza', 'hair salon', 'nail'],
    },
    'healthcare': {
        'name': 'Healthcare',
        'name_es': 'Salud',
        'description': 'Clinics, medical practices, dentists, physiotherapy',
        'description_es': 'Clínicas, consultorios médicos, dentistas, fisioterapia',
        'icon': 'medkit-outline',
        'order': 31,
        'color': '#2dd36f',
        'aliases': ['clinica', 'medico', 'dentista', 'fisioterapia', 'clinic', 'doctor', 'medical'],
    },
    'fitness': {
        'name': 'Fitness & Sports',
        'name_es': 'Fitness y Deportes',
        'description': 'Gyms, sports clubs, yoga studios, personal training',
        'description_es': 'Gimnasios, clubes deportivos, estudios de yoga, entrenamiento personal',
        'icon': 'fitness-outline',
        'order': 32,
        'color': '#f97316',
        'aliases': ['gimnasio', 'gym', 'deporte', 'yoga', 'crossfit', 'fitness'],
    },
    'consulting': {
        'name': 'Professional Services',
        'name_es': 'Servicios Profesionales',
        'description': 'Consulting, legal, accounting, agencies, freelancers',
        'description_es': 'Consultoría, legal, contabilidad, agencias, freelancers',
        'icon': 'briefcase-outline',
        'order': 33,
        'color': '#64748b',
        'aliases': ['consultoria', 'abogado', 'gestor', 'agencia', 'freelance', 'consulting', 'legal'],
    },
    'education': {
        'name': 'Education & Training',
        'name_es': 'Educación y Formación',
        'description': 'Schools, academies, training centers, tutoring, driving schools',
        'description_es': 'Escuelas, academias, centros de formación, tutorías, autoescuelas',
        'icon': 'school-outline',
        'order': 34,
        'color': '#0ea5e9',
        'aliases': ['academia', 'escuela', 'autoescuela', 'formacion', 'school', 'training'],
    },

    # -------------------------------------------------------------------------
    # Manufacturing & Industry
    # -------------------------------------------------------------------------
    'manufacturing': {
        'name': 'Manufacturing',
        'name_es': 'Manufactura',
        'description': 'Factories, production facilities, workshops',
        'description_es': 'Fábricas, instalaciones de producción, talleres industriales',
        'icon': 'construct-outline',
        'order': 40,
        'color': '#78716c',
        'aliases': ['fabrica', 'produccion', 'taller industrial', 'factory'],
    },
    'automotive': {
        'name': 'Automotive',
        'name_es': 'Automoción',
        'description': 'Car dealerships, repair shops, parts stores, car wash',
        'description_es': 'Concesionarios, talleres mecánicos, recambios, lavaderos',
        'icon': 'car-outline',
        'order': 41,
        'color': '#1e40af',
        'aliases': ['taller', 'concesionario', 'recambios', 'lavadero', 'garage', 'mechanic'],
    },
    'construction': {
        'name': 'Construction',
        'name_es': 'Construcción',
        'description': 'Contractors, construction companies, trades, hardware',
        'description_es': 'Contratistas, empresas de construcción, oficios, ferretería',
        'icon': 'hammer-outline',
        'order': 42,
        'color': '#ca8a04',
        'aliases': ['construccion', 'ferreteria', 'contratista', 'contractor', 'hardware'],
    },

    # -------------------------------------------------------------------------
    # Other
    # -------------------------------------------------------------------------
    'nonprofit': {
        'name': 'Non-Profit',
        'name_es': 'Sin Ánimo de Lucro',
        'description': 'NGOs, charities, associations, foundations, clubs',
        'description_es': 'ONGs, organizaciones benéficas, asociaciones, fundaciones, clubs',
        'icon': 'heart-outline',
        'order': 50,
        'color': '#dc2626',
        'aliases': ['ong', 'asociacion', 'fundacion', 'club', 'charity'],
    },
    'entertainment': {
        'name': 'Entertainment',
        'name_es': 'Entretenimiento',
        'description': 'Theaters, cinemas, amusement parks, gaming, escape rooms',
        'description_es': 'Teatros, cines, parques de atracciones, gaming, escape rooms',
        'icon': 'game-controller-outline',
        'order': 51,
        'color': '#7c3aed',
        'aliases': ['teatro', 'cine', 'gaming', 'escape room', 'leisure'],
    },
}

# Industry aliases for backwards compatibility
DEPRECATED_INDUSTRIES = {
    'salon': 'beauty',           # Renamed to beauty for clarity
    'professional': 'consulting',  # Renamed to consulting for clarity
}

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

# Django model choices for categories
CATEGORY_CHOICES = [
    (key, value['name']) for key, value in sorted(
        MODULE_CATEGORIES.items(),
        key=lambda x: x[1]['order']
    )
]


def get_category_info(category_id: str, language: str = 'en') -> dict:
    """
    Get category information by ID.

    Args:
        category_id: Category identifier (e.g., 'pos', 'sales')
        language: Language code ('en' or 'es')

    Returns:
        Dictionary with category info or None if not found
    """
    # Handle deprecated categories
    if category_id in DEPRECATED_CATEGORIES:
        category_id = DEPRECATED_CATEGORIES[category_id]

    if category_id not in MODULE_CATEGORIES:
        return None

    category = MODULE_CATEGORIES[category_id].copy()

    # Replace name and description with localized versions
    if language == 'es':
        category['name'] = category.get('name_es', category['name'])
        category['description'] = category.get('description_es', category['description'])

    return category


def get_all_categories(language: str = 'en') -> list:
    """
    Get all categories sorted by order.

    Args:
        language: Language code ('en' or 'es')

    Returns:
        List of category dictionaries with 'id' added
    """
    categories = []
    for category_id, category_data in sorted(
        MODULE_CATEGORIES.items(),
        key=lambda x: x[1]['order']
    ):
        category = get_category_info(category_id, language)
        category['id'] = category_id
        categories.append(category)

    return categories


def get_categories_grouped(language: str = 'en') -> dict:
    """
    Get categories grouped by business area for UI display.

    Returns:
        Dictionary with grouped categories
    """
    return {
        'core_operations': {
            'name': 'Core Operations' if language == 'en' else 'Operaciones Principales',
            'categories': ['pos', 'horeca', 'sales', 'inventory', 'purchasing', 'accounting']
        },
        'production': {
            'name': 'Production' if language == 'en' else 'Producción',
            'categories': ['manufacturing', 'quality', 'maintenance']
        },
        'customer_management': {
            'name': 'Customer Management' if language == 'en' else 'Gestión de Clientes',
            'categories': ['crm', 'marketing', 'ecommerce']
        },
        'human_resources': {
            'name': 'Human Resources' if language == 'en' else 'Recursos Humanos',
            'categories': ['hr']
        },
        'analytics': {
            'name': 'Analytics & Reports' if language == 'en' else 'Análisis y Reportes',
            'categories': ['analytics']
        },
        'collaboration': {
            'name': 'Collaboration' if language == 'en' else 'Colaboración',
            'categories': ['project', 'documents', 'website']
        },
        'technical': {
            'name': 'Technical' if language == 'en' else 'Técnico',
            'categories': ['integration', 'localization', 'utilities']
        }
    }


# =============================================================================
# INDUSTRY HELPERS
# =============================================================================

# Django model choices for industries
INDUSTRY_CHOICES = [
    (key, value['name']) for key, value in sorted(
        MODULE_INDUSTRIES.items(),
        key=lambda x: x[1]['order']
    )
]


def get_industry_info(industry_id: str, language: str = 'en') -> dict:
    """
    Get industry information by ID.

    Args:
        industry_id: Industry identifier (e.g., 'retail', 'restaurant')
        language: Language code ('en' or 'es')

    Returns:
        Dictionary with industry info or None if not found
    """
    # Handle deprecated industries
    if industry_id in DEPRECATED_INDUSTRIES:
        industry_id = DEPRECATED_INDUSTRIES[industry_id]

    if industry_id not in MODULE_INDUSTRIES:
        return None

    industry = MODULE_INDUSTRIES[industry_id].copy()

    # Replace name and description with localized versions
    if language == 'es':
        industry['name'] = industry.get('name_es', industry['name'])
        industry['description'] = industry.get('description_es', industry['description'])

    return industry


def get_all_industries(language: str = 'en') -> list:
    """
    Get all industries sorted by order.

    Args:
        language: Language code ('en' or 'es')

    Returns:
        List of industry dictionaries with 'id' added
    """
    industries = []
    for industry_id, industry_data in sorted(
        MODULE_INDUSTRIES.items(),
        key=lambda x: x[1]['order']
    ):
        industry = get_industry_info(industry_id, language)
        industry['id'] = industry_id
        industries.append(industry)

    return industries


def get_industries_grouped(language: str = 'en') -> dict:
    """
    Get industries grouped by sector for UI display.

    Returns:
        Dictionary with grouped industries
    """
    return {
        'commerce': {
            'name': 'Commerce' if language == 'en' else 'Comercio',
            'industries': ['retail', 'grocery', 'wholesale', 'ecommerce']
        },
        'specialized_retail': {
            'name': 'Specialized Retail' if language == 'en' else 'Comercio Especializado',
            'industries': ['pharmacy', 'optics', 'tobacco', 'florist', 'jewelry']
        },
        'horeca': {
            'name': 'Hospitality' if language == 'en' else 'Hostelería',
            'industries': ['restaurant', 'bar', 'cafe', 'fast_food', 'hotel', 'catering']
        },
        'services': {
            'name': 'Personal Services' if language == 'en' else 'Servicios Personales',
            'industries': ['beauty', 'healthcare', 'fitness', 'consulting', 'education']
        },
        'industry': {
            'name': 'Industry' if language == 'en' else 'Industria',
            'industries': ['manufacturing', 'automotive', 'construction']
        },
        'other': {
            'name': 'Other' if language == 'en' else 'Otros',
            'industries': ['nonprofit', 'entertainment']
        }
    }


def search_industries(query: str, language: str = 'en') -> list:
    """
    Search industries by name, description, or aliases.

    Args:
        query: Search query (e.g., "peluqueria", "restaurant")
        language: Language code ('en' or 'es')

    Returns:
        List of matching industry IDs sorted by relevance
    """
    query = query.lower().strip()
    if not query:
        return []

    matches = []

    for industry_id, industry_data in MODULE_INDUSTRIES.items():
        score = 0

        # Check exact ID match
        if query == industry_id:
            score = 100
        # Check name match
        elif query in industry_data['name'].lower():
            score = 80
        elif query in industry_data.get('name_es', '').lower():
            score = 80
        # Check description match
        elif query in industry_data['description'].lower():
            score = 50
        elif query in industry_data.get('description_es', '').lower():
            score = 50
        # Check aliases match
        else:
            aliases = industry_data.get('aliases', [])
            for alias in aliases:
                if query in alias.lower() or alias.lower() in query:
                    score = 70
                    break

        if score > 0:
            matches.append((industry_id, score))

    # Sort by score descending
    matches.sort(key=lambda x: x[1], reverse=True)

    return [m[0] for m in matches]


def normalize_industry(industry_id: str) -> str:
    """
    Normalize an industry ID, handling deprecations.

    Args:
        industry_id: Industry identifier

    Returns:
        Normalized industry ID
    """
    if industry_id in DEPRECATED_INDUSTRIES:
        return DEPRECATED_INDUSTRIES[industry_id]
    return industry_id


def normalize_category(category_id: str) -> str:
    """
    Normalize a category ID, handling deprecations.

    Args:
        category_id: Category identifier

    Returns:
        Normalized category ID
    """
    if category_id in DEPRECATED_CATEGORIES:
        return DEPRECATED_CATEGORIES[category_id]
    return category_id
