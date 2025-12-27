"""
Module Categories and Industries Configuration

Defines all available categories and industries for ERPlora modules.
This file is shared between Cloud (marketplace) and Hub (module management).

Classification System (3 levels):
1. CATEGORY (1 per module) - Functional category (what the module does)
2. INDUSTRIES (multiple) - Business verticals (who uses it)
3. TAGS (multiple) - Free keywords for search

Based on: hub/modules/MODULE_CATALOG.md
"""

MODULE_CATEGORIES = {
    'pos': {
        'name': 'Point of Sale (POS)',
        'name_es': 'Punto de Venta (POS)',
        'description': 'Point of sale systems for physical retail and restaurants',
        'description_es': 'Sistemas de punto de venta para retail físico y restaurantes',
        'icon': 'cash-outline',
        'order': 1,
        'color': '#3880ff',  # primary
    },
    'hospitality': {
        'name': 'Hospitality',
        'name_es': 'Hostelería',
        'description': 'Solutions for bars, restaurants, hotels, and hospitality businesses',
        'description_es': 'Soluciones para bares, restaurantes, hoteles y negocios de hostelería',
        'icon': 'restaurant-outline',
        'order': 2,
        'color': '#ff6b35',
    },
    'sales': {
        'name': 'Sales',
        'name_es': 'Ventas',
        'description': 'Sales management, quotations, orders, invoicing',
        'description_es': 'Gestión de ventas, cotizaciones, pedidos, facturación',
        'icon': 'trending-up-outline',
        'order': 3,
        'color': '#5260ff',
    },
    'inventory': {
        'name': 'Inventory',
        'name_es': 'Inventario',
        'description': 'Stock management, warehouses, transfers',
        'description_es': 'Gestión de stock, almacenes, transferencias',
        'icon': 'cube-outline',
        'order': 4,
        'color': '#3dc2ff',  # secondary
    },
    'purchasing': {
        'name': 'Purchasing',
        'name_es': 'Compras',
        'description': 'Purchase orders, supplier management, procurement',
        'description_es': 'Órdenes de compra, gestión de proveedores, aprovisionamiento',
        'icon': 'cart-outline',
        'order': 5,
        'color': '#5260ff',
    },
    'accounting': {
        'name': 'Accounting',
        'name_es': 'Contabilidad',
        'description': 'Financial management, general ledger, reconciliation',
        'description_es': 'Gestión financiera, libro mayor, conciliación',
        'icon': 'calculator-outline',
        'order': 6,
        'color': '#2dd36f',  # success
    },
    'manufacturing': {
        'name': 'Manufacturing',
        'name_es': 'Manufactura',
        'description': 'Production planning, MRP, work orders',
        'description_es': 'Planificación de producción, MRP, órdenes de trabajo',
        'icon': 'construct-outline',
        'order': 7,
        'color': '#ffc409',  # warning
    },
    'quality': {
        'name': 'Quality',
        'name_es': 'Calidad',
        'description': 'Quality control, inspections, certifications',
        'description_es': 'Control de calidad, inspecciones, certificaciones',
        'icon': 'checkmark-circle-outline',
        'order': 8,
        'color': '#2dd36f',
    },
    'maintenance': {
        'name': 'Maintenance',
        'name_es': 'Mantenimiento',
        'description': 'Asset maintenance, preventive maintenance, repairs',
        'description_es': 'Mantenimiento de activos, mantenimiento preventivo, reparaciones',
        'icon': 'build-outline',
        'order': 9,
        'color': '#ffc409',
    },
    'crm': {
        'name': 'CRM',
        'name_es': 'CRM',
        'description': 'Customer relationship management, leads, opportunities',
        'description_es': 'Gestión de relaciones con clientes, prospectos, oportunidades',
        'icon': 'people-outline',
        'order': 10,
        'color': '#eb445a',  # danger
    },
    'marketing': {
        'name': 'Marketing',
        'name_es': 'Marketing',
        'description': 'Campaigns, automation, social media',
        'description_es': 'Campañas, automatización, redes sociales',
        'icon': 'megaphone-outline',
        'order': 11,
        'color': '#eb445a',
    },
    'ecommerce': {
        'name': 'E-Commerce',
        'name_es': 'Comercio Electrónico',
        'description': 'Online stores, shopping carts, payment gateways',
        'description_es': 'Tiendas online, carritos de compra, pasarelas de pago',
        'icon': 'storefront-outline',
        'order': 12,
        'color': '#3880ff',
    },
    'hr': {
        'name': 'Human Resources',
        'name_es': 'Recursos Humanos',
        'description': 'Employee management, payroll, attendance',
        'description_es': 'Gestión de empleados, nómina, asistencia',
        'icon': 'person-outline',
        'order': 13,
        'color': '#5260ff',
    },
    'recruitment': {
        'name': 'Recruitment',
        'name_es': 'Reclutamiento',
        'description': 'Job postings, applicant tracking, interviews',
        'description_es': 'Publicación de empleos, seguimiento de candidatos, entrevistas',
        'icon': 'briefcase-outline',
        'order': 14,
        'color': '#5260ff',
    },
    'reporting': {
        'name': 'Reporting',
        'name_es': 'Reportes',
        'description': 'Report generation, custom reports, exports',
        'description_es': 'Generación de reportes, reportes personalizados, exportaciones',
        'icon': 'bar-chart-outline',
        'order': 15,
        'color': '#3dc2ff',
    },
    'analytics': {
        'name': 'Analytics',
        'name_es': 'Análisis',
        'description': 'Business intelligence, dashboards, KPIs',
        'description_es': 'Inteligencia de negocios, tableros, KPIs',
        'icon': 'analytics-outline',
        'order': 16,
        'color': '#3dc2ff',
    },
    'project': {
        'name': 'Project Management',
        'name_es': 'Gestión de Proyectos',
        'description': 'Projects, tasks, time tracking, budgets',
        'description_es': 'Proyectos, tareas, seguimiento de tiempo, presupuestos',
        'icon': 'git-branch-outline',
        'order': 17,
        'color': '#92949c',  # medium
    },
    'documents': {
        'name': 'Documents',
        'name_es': 'Documentos',
        'description': 'Document management, templates, digital signatures',
        'description_es': 'Gestión de documentos, plantillas, firmas digitales',
        'icon': 'document-text-outline',
        'order': 18,
        'color': '#92949c',
    },
    'website': {
        'name': 'Website',
        'name_es': 'Sitio Web',
        'description': 'Website builder, CMS, landing pages',
        'description_es': 'Constructor de sitios web, CMS, páginas de aterrizaje',
        'icon': 'globe-outline',
        'order': 19,
        'color': '#3880ff',
    },
    'integration': {
        'name': 'Integration',
        'name_es': 'Integración',
        'description': 'Third-party integrations, APIs, webhooks',
        'description_es': 'Integraciones con terceros, APIs, webhooks',
        'icon': 'swap-horizontal-outline',
        'order': 20,
        'color': '#92949c',
    },
    'legal': {
        'name': 'Legal & Compliance',
        'name_es': 'Legal y Cumplimiento',
        'description': 'Legal documents, compliance, regulations',
        'description_es': 'Documentos legales, cumplimiento, regulaciones',
        'icon': 'shield-checkmark-outline',
        'order': 21,
        'color': '#2dd36f',
    },
    'localization': {
        'name': 'Localization',
        'name_es': 'Localización',
        'description': 'Country-specific features, tax regulations, invoicing',
        'description_es': 'Funcionalidades específicas por país, regulaciones fiscales, facturación',
        'icon': 'location-outline',
        'order': 22,
        'color': '#ffc409',
    },
    'utilities': {
        'name': 'Utilities',
        'name_es': 'Utilidades',
        'description': 'General utilities, tools, helpers',
        'description_es': 'Utilidades generales, herramientas, ayudantes',
        'icon': 'settings-outline',
        'order': 23,
        'color': '#92949c',
    },
}

# =============================================================================
# INDUSTRIES - Business verticals (who uses the module)
# =============================================================================

MODULE_INDUSTRIES = {
    # Retail & Commerce
    'retail': {
        'name': 'Retail',
        'name_es': 'Comercio Minorista',
        'description': 'Retail stores, shops, boutiques',
        'description_es': 'Tiendas minoristas, comercios, boutiques',
        'icon': 'storefront-outline',
        'order': 1,
        'color': '#3880ff',
    },
    'wholesale': {
        'name': 'Wholesale',
        'name_es': 'Mayorista',
        'description': 'Wholesale distributors and B2B sales',
        'description_es': 'Distribuidores mayoristas y ventas B2B',
        'icon': 'business-outline',
        'order': 2,
        'color': '#5260ff',
    },
    'ecommerce': {
        'name': 'E-Commerce',
        'name_es': 'Comercio Electrónico',
        'description': 'Online stores and digital commerce',
        'description_es': 'Tiendas online y comercio digital',
        'icon': 'globe-outline',
        'order': 3,
        'color': '#3dc2ff',
    },

    # Food & Hospitality
    'restaurant': {
        'name': 'Restaurants',
        'name_es': 'Restaurantes',
        'description': 'Full-service restaurants and dining',
        'description_es': 'Restaurantes de servicio completo',
        'icon': 'restaurant-outline',
        'order': 10,
        'color': '#ff6b35',
    },
    'bar': {
        'name': 'Bars & Pubs',
        'name_es': 'Bares y Pubs',
        'description': 'Bars, pubs, nightclubs, lounges',
        'description_es': 'Bares, pubs, discotecas, lounges',
        'icon': 'wine-outline',
        'order': 11,
        'color': '#eb445a',
    },
    'cafe': {
        'name': 'Cafes & Bakeries',
        'name_es': 'Cafeterías y Panaderías',
        'description': 'Coffee shops, bakeries, pastry shops',
        'description_es': 'Cafeterías, panaderías, pastelerías',
        'icon': 'cafe-outline',
        'order': 12,
        'color': '#92400e',
    },
    'fast_food': {
        'name': 'Fast Food & QSR',
        'name_es': 'Comida Rápida',
        'description': 'Fast food, quick service restaurants, food trucks',
        'description_es': 'Comida rápida, restaurantes de servicio rápido, food trucks',
        'icon': 'fast-food-outline',
        'order': 13,
        'color': '#ffc409',
    },
    'hotel': {
        'name': 'Hotels & Lodging',
        'name_es': 'Hoteles y Alojamiento',
        'description': 'Hotels, hostels, B&Bs, vacation rentals',
        'description_es': 'Hoteles, hostales, B&Bs, alquileres vacacionales',
        'icon': 'bed-outline',
        'order': 14,
        'color': '#6366f1',
    },
    'catering': {
        'name': 'Catering & Events',
        'name_es': 'Catering y Eventos',
        'description': 'Catering services, event planning, banquets',
        'description_es': 'Servicios de catering, planificación de eventos, banquetes',
        'icon': 'people-outline',
        'order': 15,
        'color': '#ec4899',
    },

    # Services
    'salon': {
        'name': 'Beauty & Wellness',
        'name_es': 'Belleza y Bienestar',
        'description': 'Hair salons, spas, nail salons, wellness centers',
        'description_es': 'Peluquerías, spas, salones de uñas, centros de bienestar',
        'icon': 'cut-outline',
        'order': 20,
        'color': '#f472b6',
    },
    'healthcare': {
        'name': 'Healthcare',
        'name_es': 'Salud',
        'description': 'Clinics, pharmacies, medical practices',
        'description_es': 'Clínicas, farmacias, consultorios médicos',
        'icon': 'medkit-outline',
        'order': 21,
        'color': '#2dd36f',
    },
    'fitness': {
        'name': 'Fitness & Sports',
        'name_es': 'Fitness y Deportes',
        'description': 'Gyms, sports clubs, fitness centers',
        'description_es': 'Gimnasios, clubes deportivos, centros de fitness',
        'icon': 'fitness-outline',
        'order': 22,
        'color': '#f97316',
    },
    'professional': {
        'name': 'Professional Services',
        'name_es': 'Servicios Profesionales',
        'description': 'Consulting, legal, accounting, agencies',
        'description_es': 'Consultoría, legal, contabilidad, agencias',
        'icon': 'briefcase-outline',
        'order': 23,
        'color': '#64748b',
    },
    'education': {
        'name': 'Education',
        'name_es': 'Educación',
        'description': 'Schools, academies, training centers, tutoring',
        'description_es': 'Escuelas, academias, centros de formación, tutorías',
        'icon': 'school-outline',
        'order': 24,
        'color': '#0ea5e9',
    },

    # Manufacturing & Industry
    'manufacturing': {
        'name': 'Manufacturing',
        'name_es': 'Manufactura',
        'description': 'Factories, production facilities, workshops',
        'description_es': 'Fábricas, instalaciones de producción, talleres',
        'icon': 'construct-outline',
        'order': 30,
        'color': '#78716c',
    },
    'automotive': {
        'name': 'Automotive',
        'name_es': 'Automoción',
        'description': 'Car dealerships, repair shops, parts stores',
        'description_es': 'Concesionarios, talleres mecánicos, tiendas de recambios',
        'icon': 'car-outline',
        'order': 31,
        'color': '#1e40af',
    },
    'construction': {
        'name': 'Construction',
        'name_es': 'Construcción',
        'description': 'Contractors, construction companies, trades',
        'description_es': 'Contratistas, empresas de construcción, oficios',
        'icon': 'hammer-outline',
        'order': 32,
        'color': '#ca8a04',
    },

    # Other
    'nonprofit': {
        'name': 'Non-Profit',
        'name_es': 'Sin Ánimo de Lucro',
        'description': 'NGOs, charities, associations, foundations',
        'description_es': 'ONGs, organizaciones benéficas, asociaciones, fundaciones',
        'icon': 'heart-outline',
        'order': 40,
        'color': '#dc2626',
    },
    'entertainment': {
        'name': 'Entertainment',
        'name_es': 'Entretenimiento',
        'description': 'Theaters, cinemas, amusement parks, gaming',
        'description_es': 'Teatros, cines, parques de atracciones, gaming',
        'icon': 'game-controller-outline',
        'order': 41,
        'color': '#7c3aed',
    },
}

# Django model choices for categories
CATEGORY_CHOICES = [
    (key, value['name']) for key, value in sorted(
        MODULE_CATEGORIES.items(),
        key=lambda x: x[1]['order']
    )
]

# Helper function to get category info
def get_category_info(category_id: str, language: str = 'en') -> dict:
    """
    Get category information by ID.

    Args:
        category_id: Category identifier (e.g., 'pos', 'sales')
        language: Language code ('en' or 'es')

    Returns:
        Dictionary with category info
    """
    if category_id not in MODULE_CATEGORIES:
        return None

    category = MODULE_CATEGORIES[category_id].copy()

    # Replace name and description with localized versions
    if language == 'es':
        category['name'] = category.get('name_es', category['name'])
        category['description'] = category.get('description_es', category['description'])

    return category


# Helper function to get all categories sorted by order
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


# Helper function to get categories grouped for UI
def get_categories_grouped(language: str = 'en') -> dict:
    """
    Get categories grouped by business area for UI display.

    Returns:
        Dictionary with grouped categories
    """
    return {
        'core_operations': {
            'name': 'Core Operations' if language == 'en' else 'Operaciones Principales',
            'categories': ['pos', 'hospitality', 'sales', 'inventory', 'purchasing', 'accounting']
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
            'categories': ['hr', 'recruitment']
        },
        'analytics': {
            'name': 'Analytics & Reports' if language == 'en' else 'Análisis y Reportes',
            'categories': ['reporting', 'analytics']
        },
        'collaboration': {
            'name': 'Collaboration' if language == 'en' else 'Colaboración',
            'categories': ['project', 'documents', 'website']
        },
        'technical': {
            'name': 'Technical' if language == 'en' else 'Técnico',
            'categories': ['integration', 'legal', 'localization', 'utilities']
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
        Dictionary with industry info
    """
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
            'industries': ['retail', 'wholesale', 'ecommerce']
        },
        'food_hospitality': {
            'name': 'Food & Hospitality' if language == 'en' else 'Alimentación y Hostelería',
            'industries': ['restaurant', 'bar', 'cafe', 'fast_food', 'hotel', 'catering']
        },
        'services': {
            'name': 'Services' if language == 'en' else 'Servicios',
            'industries': ['salon', 'healthcare', 'fitness', 'professional', 'education']
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
