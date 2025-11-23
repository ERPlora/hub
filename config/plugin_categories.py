"""
Plugin Categories Configuration

Defines all available categories for ERPlora plugins.
This file is shared between Cloud (marketplace) and Hub (plugin management).

Based on: hub/plugins/PLUGIN_CATALOG.md
"""

PLUGIN_CATEGORIES = {
    'pos': {
        'name': 'Point of Sale (POS)',
        'name_es': 'Punto de Venta (POS)',
        'description': 'Point of sale systems for physical retail and restaurants',
        'description_es': 'Sistemas de punto de venta para retail físico y restaurantes',
        'icon': 'cash-outline',
        'order': 1,
        'color': '#3880ff',  # primary
    },
    'sales': {
        'name': 'Sales',
        'name_es': 'Ventas',
        'description': 'Sales management, quotations, orders, invoicing',
        'description_es': 'Gestión de ventas, cotizaciones, pedidos, facturación',
        'icon': 'trending-up-outline',
        'order': 2,
        'color': '#5260ff',
    },
    'inventory': {
        'name': 'Inventory',
        'name_es': 'Inventario',
        'description': 'Stock management, warehouses, transfers',
        'description_es': 'Gestión de stock, almacenes, transferencias',
        'icon': 'cube-outline',
        'order': 3,
        'color': '#3dc2ff',  # secondary
    },
    'purchasing': {
        'name': 'Purchasing',
        'name_es': 'Compras',
        'description': 'Purchase orders, supplier management, procurement',
        'description_es': 'Órdenes de compra, gestión de proveedores, aprovisionamiento',
        'icon': 'cart-outline',
        'order': 4,
        'color': '#5260ff',
    },
    'accounting': {
        'name': 'Accounting',
        'name_es': 'Contabilidad',
        'description': 'Financial management, general ledger, reconciliation',
        'description_es': 'Gestión financiera, libro mayor, conciliación',
        'icon': 'calculator-outline',
        'order': 5,
        'color': '#2dd36f',  # success
    },
    'manufacturing': {
        'name': 'Manufacturing',
        'name_es': 'Manufactura',
        'description': 'Production planning, MRP, work orders',
        'description_es': 'Planificación de producción, MRP, órdenes de trabajo',
        'icon': 'construct-outline',
        'order': 6,
        'color': '#ffc409',  # warning
    },
    'quality': {
        'name': 'Quality',
        'name_es': 'Calidad',
        'description': 'Quality control, inspections, certifications',
        'description_es': 'Control de calidad, inspecciones, certificaciones',
        'icon': 'checkmark-circle-outline',
        'order': 7,
        'color': '#2dd36f',
    },
    'maintenance': {
        'name': 'Maintenance',
        'name_es': 'Mantenimiento',
        'description': 'Asset maintenance, preventive maintenance, repairs',
        'description_es': 'Mantenimiento de activos, mantenimiento preventivo, reparaciones',
        'icon': 'build-outline',
        'order': 8,
        'color': '#ffc409',
    },
    'crm': {
        'name': 'CRM',
        'name_es': 'CRM',
        'description': 'Customer relationship management, leads, opportunities',
        'description_es': 'Gestión de relaciones con clientes, prospectos, oportunidades',
        'icon': 'people-outline',
        'order': 9,
        'color': '#eb445a',  # danger
    },
    'marketing': {
        'name': 'Marketing',
        'name_es': 'Marketing',
        'description': 'Campaigns, automation, social media',
        'description_es': 'Campañas, automatización, redes sociales',
        'icon': 'megaphone-outline',
        'order': 10,
        'color': '#eb445a',
    },
    'ecommerce': {
        'name': 'E-Commerce',
        'name_es': 'Comercio Electrónico',
        'description': 'Online stores, shopping carts, payment gateways',
        'description_es': 'Tiendas online, carritos de compra, pasarelas de pago',
        'icon': 'storefront-outline',
        'order': 11,
        'color': '#3880ff',
    },
    'hr': {
        'name': 'Human Resources',
        'name_es': 'Recursos Humanos',
        'description': 'Employee management, payroll, attendance',
        'description_es': 'Gestión de empleados, nómina, asistencia',
        'icon': 'person-outline',
        'order': 12,
        'color': '#5260ff',
    },
    'recruitment': {
        'name': 'Recruitment',
        'name_es': 'Reclutamiento',
        'description': 'Job postings, applicant tracking, interviews',
        'description_es': 'Publicación de empleos, seguimiento de candidatos, entrevistas',
        'icon': 'briefcase-outline',
        'order': 13,
        'color': '#5260ff',
    },
    'reporting': {
        'name': 'Reporting',
        'name_es': 'Reportes',
        'description': 'Report generation, custom reports, exports',
        'description_es': 'Generación de reportes, reportes personalizados, exportaciones',
        'icon': 'bar-chart-outline',
        'order': 14,
        'color': '#3dc2ff',
    },
    'analytics': {
        'name': 'Analytics',
        'name_es': 'Análisis',
        'description': 'Business intelligence, dashboards, KPIs',
        'description_es': 'Inteligencia de negocios, tableros, KPIs',
        'icon': 'analytics-outline',
        'order': 15,
        'color': '#3dc2ff',
    },
    'project': {
        'name': 'Project Management',
        'name_es': 'Gestión de Proyectos',
        'description': 'Projects, tasks, time tracking, budgets',
        'description_es': 'Proyectos, tareas, seguimiento de tiempo, presupuestos',
        'icon': 'git-branch-outline',
        'order': 16,
        'color': '#92949c',  # medium
    },
    'documents': {
        'name': 'Documents',
        'name_es': 'Documentos',
        'description': 'Document management, templates, digital signatures',
        'description_es': 'Gestión de documentos, plantillas, firmas digitales',
        'icon': 'document-text-outline',
        'order': 17,
        'color': '#92949c',
    },
    'website': {
        'name': 'Website',
        'name_es': 'Sitio Web',
        'description': 'Website builder, CMS, landing pages',
        'description_es': 'Constructor de sitios web, CMS, páginas de aterrizaje',
        'icon': 'globe-outline',
        'order': 18,
        'color': '#3880ff',
    },
    'integration': {
        'name': 'Integration',
        'name_es': 'Integración',
        'description': 'Third-party integrations, APIs, webhooks',
        'description_es': 'Integraciones con terceros, APIs, webhooks',
        'icon': 'swap-horizontal-outline',
        'order': 19,
        'color': '#92949c',
    },
    'legal': {
        'name': 'Legal & Compliance',
        'name_es': 'Legal y Cumplimiento',
        'description': 'Legal documents, compliance, regulations',
        'description_es': 'Documentos legales, cumplimiento, regulaciones',
        'icon': 'shield-checkmark-outline',
        'order': 20,
        'color': '#2dd36f',
    },
    'localization': {
        'name': 'Localization',
        'name_es': 'Localización',
        'description': 'Country-specific features, tax regulations, invoicing',
        'description_es': 'Funcionalidades específicas por país, regulaciones fiscales, facturación',
        'icon': 'location-outline',
        'order': 21,
        'color': '#ffc409',
    },
    'utilities': {
        'name': 'Utilities',
        'name_es': 'Utilidades',
        'description': 'General utilities, tools, helpers',
        'description_es': 'Utilidades generales, herramientas, ayudantes',
        'icon': 'settings-outline',
        'order': 22,
        'color': '#92949c',
    },
}

# Django model choices
CATEGORY_CHOICES = [
    (key, value['name']) for key, value in sorted(
        PLUGIN_CATEGORIES.items(),
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
    if category_id not in PLUGIN_CATEGORIES:
        return None

    category = PLUGIN_CATEGORIES[category_id].copy()

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
        PLUGIN_CATEGORIES.items(),
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
            'categories': ['pos', 'sales', 'inventory', 'purchasing', 'accounting']
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
