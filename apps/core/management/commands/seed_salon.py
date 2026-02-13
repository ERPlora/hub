"""
Seed demo data for a hair salon POS setup.

Creates service categories, services, customers, customer groups,
and sample appointments to test the customer ficha.

Usage:
    python manage.py seed_salon
    python manage.py seed_salon --flush   # delete existing seed data first
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'Seed demo data for a hair salon (categories, services, customers, appointments)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--flush', action='store_true',
            help='Delete existing seed data before creating new data',
        )

    def handle(self, *args, **options):
        flush = options['flush']

        # --- Service Categories & Services ---
        try:
            from services.models import ServiceCategory, Service
        except ImportError:
            self.stderr.write(self.style.ERROR('Services module not available'))
            return

        if flush:
            self.stdout.write('Flushing existing seed data...')
            Service.all_objects.filter(notes='seed_salon').delete()
            ServiceCategory.all_objects.filter(description='seed_salon').delete()

        categories = self._create_categories(ServiceCategory)
        services = self._create_services(Service, categories)

        # --- Customer Groups & Customers ---
        try:
            from customers.models import CustomerGroup, Customer
        except ImportError:
            self.stderr.write(self.style.ERROR('Customers module not available'))
            return

        if flush:
            Customer.all_objects.filter(notes='seed_salon').delete()
            CustomerGroup.all_objects.filter(description='seed_salon').delete()

        groups = self._create_groups(CustomerGroup)
        customers = self._create_customers(Customer, groups)

        # --- Appointments ---
        try:
            from appointments.models import Appointment
        except ImportError:
            self.stderr.write(self.style.WARNING('Appointments module not available — skipping'))
            Appointment = None

        if Appointment:
            if flush:
                Appointment.all_objects.filter(internal_notes='seed_salon').delete()
            self._create_appointments(Appointment, customers, services)

        self.stdout.write(self.style.SUCCESS('Salon seed data created successfully!'))

    # ===================================================================
    # Categories
    # ===================================================================

    def _create_categories(self, ServiceCategory):
        data = [
            {'name': 'Corte', 'slug': 'corte', 'icon': 'cut-outline', 'color': '#3B82F6', 'sort_order': 1},
            {'name': 'Coloracion', 'slug': 'coloracion', 'icon': 'color-palette-outline', 'color': '#EC4899', 'sort_order': 2},
            {'name': 'Peinado', 'slug': 'peinado', 'icon': 'brush-outline', 'color': '#8B5CF6', 'sort_order': 3},
            {'name': 'Tratamientos', 'slug': 'tratamientos', 'icon': 'flask-outline', 'color': '#10B981', 'sort_order': 4},
            {'name': 'Barba', 'slug': 'barba', 'icon': 'man-outline', 'color': '#F59E0B', 'sort_order': 5},
            {'name': 'Varios', 'slug': 'varios', 'icon': 'ellipsis-horizontal-outline', 'color': '#6B7280', 'sort_order': 6},
        ]
        categories = {}
        for item in data:
            cat, created = ServiceCategory.all_objects.get_or_create(
                slug=item['slug'],
                defaults={**item, 'description': 'seed_salon'},
            )
            categories[item['slug']] = cat
            status = 'created' if created else 'exists'
            self.stdout.write(f'  Category: {cat.name} [{status}]')
        return categories

    # ===================================================================
    # Services
    # ===================================================================

    def _create_services(self, Service, categories):
        data = [
            # Corte
            {'name': 'Corte mujer', 'slug': 'corte-mujer', 'category': 'corte', 'price': '25.00', 'duration': 45, 'short_description': 'Incluye lavado y secado'},
            {'name': 'Corte hombre', 'slug': 'corte-hombre', 'category': 'corte', 'price': '15.00', 'duration': 30},
            {'name': 'Corte nino', 'slug': 'corte-nino', 'category': 'corte', 'price': '12.00', 'duration': 20, 'short_description': 'Menores de 12 anos'},
            {'name': 'Solo flequillo', 'slug': 'solo-flequillo', 'category': 'corte', 'price': '5.00', 'duration': 10},
            # Coloracion
            {'name': 'Tinte raiz', 'slug': 'tinte-raiz', 'category': 'coloracion', 'price': '30.00', 'duration': 60, 'pricing_type': 'from'},
            {'name': 'Tinte completo', 'slug': 'tinte-completo', 'category': 'coloracion', 'price': '45.00', 'duration': 90},
            {'name': 'Mechas parciales', 'slug': 'mechas-parciales', 'category': 'coloracion', 'price': '40.00', 'duration': 90},
            {'name': 'Mechas completas', 'slug': 'mechas-completas', 'category': 'coloracion', 'price': '55.00', 'duration': 120},
            {'name': 'Balayage', 'slug': 'balayage', 'category': 'coloracion', 'price': '70.00', 'duration': 150},
            {'name': 'Decoloracion', 'slug': 'decoloracion', 'category': 'coloracion', 'price': '40.00', 'duration': 90, 'pricing_type': 'from'},
            # Peinado
            {'name': 'Brushing', 'slug': 'brushing', 'category': 'peinado', 'price': '15.00', 'duration': 30},
            {'name': 'Recogido', 'slug': 'recogido', 'category': 'peinado', 'price': '35.00', 'duration': 45},
            {'name': 'Peinado evento', 'slug': 'peinado-evento', 'category': 'peinado', 'price': '50.00', 'duration': 60},
            # Tratamientos
            {'name': 'Hidratacion profunda', 'slug': 'hidratacion-profunda', 'category': 'tratamientos', 'price': '20.00', 'duration': 30},
            {'name': 'Keratina', 'slug': 'keratina', 'category': 'tratamientos', 'price': '80.00', 'duration': 120},
            {'name': 'Botox capilar', 'slug': 'botox-capilar', 'category': 'tratamientos', 'price': '60.00', 'duration': 90},
            # Barba
            {'name': 'Recorte barba', 'slug': 'recorte-barba', 'category': 'barba', 'price': '10.00', 'duration': 15},
            {'name': 'Afeitado clasico', 'slug': 'afeitado-clasico', 'category': 'barba', 'price': '15.00', 'duration': 20},
            {'name': 'Diseno barba', 'slug': 'diseno-barba', 'category': 'barba', 'price': '12.00', 'duration': 20},
            # Varios
            {'name': 'Lavado + secado', 'slug': 'lavado-secado', 'category': 'varios', 'price': '8.00', 'duration': 15},
            {'name': 'Depilacion cejas', 'slug': 'depilacion-cejas', 'category': 'varios', 'price': '6.00', 'duration': 10},
        ]

        services = {}
        for item in data:
            cat = categories.get(item.pop('category'))
            duration = item.pop('duration')
            pricing_type = item.pop('pricing_type', 'fixed')
            short_desc = item.pop('short_description', '')
            svc, created = Service.all_objects.get_or_create(
                slug=item['slug'],
                defaults={
                    'name': item['name'],
                    'slug': item['slug'],
                    'category': cat,
                    'price': Decimal(item['price']),
                    'duration_minutes': duration,
                    'pricing_type': pricing_type,
                    'short_description': short_desc,
                    'notes': 'seed_salon',
                },
            )
            services[item['slug']] = svc
            status = 'created' if created else 'exists'
            self.stdout.write(f'  Service: {svc.name} ({svc.price}EUR, {svc.duration_minutes}min) [{status}]')
        return services

    # ===================================================================
    # Customer Groups
    # ===================================================================

    def _create_groups(self, CustomerGroup):
        data = [
            {'name': 'VIP', 'color': 'success', 'discount_percent': '10.00', 'sort_order': 1},
            {'name': 'Frecuente', 'color': 'primary', 'discount_percent': '5.00', 'sort_order': 2},
            {'name': 'Nuevo', 'color': 'warning', 'discount_percent': '0.00', 'sort_order': 3},
        ]
        groups = {}
        for item in data:
            grp, created = CustomerGroup.all_objects.get_or_create(
                name=item['name'],
                defaults={**item, 'description': 'seed_salon'},
            )
            groups[item['name']] = grp
            status = 'created' if created else 'exists'
            self.stdout.write(f'  Group: {grp.name} [{status}]')
        return groups

    # ===================================================================
    # Customers
    # ===================================================================

    def _create_customers(self, Customer, groups):
        data = [
            {
                'name': 'Maria Garcia Lopez',
                'phone': '612 345 678',
                'email': 'maria.garcia@email.com',
                'tax_id': '12345678A',
                'address': 'Calle Mayor 15, 2o B',
                'city': 'Madrid',
                'postal_code': '28001',
                'country': 'Espana',
                'notes': 'Tinte: 6.1 + 7.3 oxidante 20vol\nPrefiere secador a temperatura media\nAlergia al amoniaco — usar tintes sin amoniaco',
                'groups': ['VIP'],
                'total_purchases': 24,
                'total_spent': '1250.00',
            },
            {
                'name': 'Ana Martinez Ruiz',
                'phone': '634 567 890',
                'email': 'ana.martinez@email.com',
                'address': 'Avenida de la Constitucion 42',
                'city': 'Madrid',
                'postal_code': '28004',
                'country': 'Espana',
                'notes': 'Pelo muy fino — cuidado con decoloraciones\nBalayage cada 3 meses\nColor formula: 8.0 + 9.1 oxidante 10vol',
                'groups': ['VIP'],
                'total_purchases': 18,
                'total_spent': '980.00',
            },
            {
                'name': 'Carlos Fernandez Diaz',
                'phone': '655 123 456',
                'email': 'carlos.f@email.com',
                'city': 'Madrid',
                'postal_code': '28010',
                'country': 'Espana',
                'notes': 'Corte degradado #2 laterales\nBarba recorte cada 2 semanas',
                'groups': ['Frecuente'],
                'total_purchases': 15,
                'total_spent': '375.00',
            },
            {
                'name': 'Laura Sanchez Moreno',
                'phone': '678 901 234',
                'email': 'laura.sanchez@email.com',
                'address': 'Plaza Espana 8, 1o A',
                'city': 'Madrid',
                'postal_code': '28008',
                'country': 'Espana',
                'notes': 'Keratina cada 4 meses\nNo usar productos con parabenos\nPelo rizado natural',
                'groups': ['Frecuente'],
                'total_purchases': 10,
                'total_spent': '620.00',
            },
            {
                'name': 'Pedro Gomez Torres',
                'phone': '699 876 543',
                'notes': 'Cliente nuevo — referido por Maria Garcia\nCorte clasico, no le gusta muy corto',
                'groups': ['Nuevo'],
                'total_purchases': 2,
                'total_spent': '30.00',
            },
            {
                'name': 'Sofia Rodriguez Navarro',
                'phone': '611 222 333',
                'email': 'sofia.rn@email.com',
                'city': 'Madrid',
                'postal_code': '28002',
                'country': 'Espana',
                'notes': 'Mechas rubias tipo babylights\nUsa champu morado en casa\nFormula: decoloracion + matiz 10.21',
                'groups': ['Frecuente'],
                'total_purchases': 8,
                'total_spent': '520.00',
            },
        ]

        customers = {}
        for item in data:
            group_names = item.pop('groups', [])
            total_purchases = item.pop('total_purchases', 0)
            total_spent = item.pop('total_spent', '0.00')

            cust, created = Customer.all_objects.get_or_create(
                name=item['name'],
                defaults={
                    **item,
                    'notes': item.get('notes', '') + '\n\n[seed_salon]' if item.get('notes') else 'seed_salon',
                    'total_purchases': total_purchases,
                    'total_spent': Decimal(total_spent),
                },
            )
            if created:
                for gname in group_names:
                    grp = groups.get(gname)
                    if grp:
                        cust.groups.add(grp)

            customers[item['name']] = cust
            status = 'created' if created else 'exists'
            self.stdout.write(f'  Customer: {cust.name} [{status}]')
        return customers

    # ===================================================================
    # Appointments
    # ===================================================================

    def _create_appointments(self, Appointment, customers, services):
        now = timezone.now()
        today_9am = now.replace(hour=9, minute=0, second=0, microsecond=0)

        # Build appointment data — mix of past completed, past no-show, and upcoming
        data = [
            # Maria Garcia — regular VIP client with rich history
            {'customer': 'Maria Garcia Lopez', 'service': 'tinte-raiz', 'days_ago': 7, 'hour': 10, 'status': 'completed'},
            {'customer': 'Maria Garcia Lopez', 'service': 'corte-mujer', 'days_ago': 7, 'hour': 11, 'status': 'completed'},
            {'customer': 'Maria Garcia Lopez', 'service': 'hidratacion-profunda', 'days_ago': 35, 'hour': 10, 'status': 'completed'},
            {'customer': 'Maria Garcia Lopez', 'service': 'tinte-raiz', 'days_ago': 35, 'hour': 10, 'minute': 30, 'status': 'completed'},
            {'customer': 'Maria Garcia Lopez', 'service': 'brushing', 'days_ago': 60, 'hour': 16, 'status': 'completed'},
            {'customer': 'Maria Garcia Lopez', 'service': 'corte-mujer', 'days_ago': 60, 'hour': 15, 'status': 'completed'},
            # Maria — upcoming appointment
            {'customer': 'Maria Garcia Lopez', 'service': 'tinte-raiz', 'days_ago': -5, 'hour': 10, 'status': 'confirmed'},

            # Ana Martinez — balayage client
            {'customer': 'Ana Martinez Ruiz', 'service': 'balayage', 'days_ago': 14, 'hour': 9, 'status': 'completed'},
            {'customer': 'Ana Martinez Ruiz', 'service': 'corte-mujer', 'days_ago': 14, 'hour': 12, 'status': 'completed'},
            {'customer': 'Ana Martinez Ruiz', 'service': 'botox-capilar', 'days_ago': 45, 'hour': 11, 'status': 'completed'},
            {'customer': 'Ana Martinez Ruiz', 'service': 'brushing', 'days_ago': 3, 'hour': 17, 'status': 'completed'},

            # Carlos — barber client
            {'customer': 'Carlos Fernandez Diaz', 'service': 'corte-hombre', 'days_ago': 5, 'hour': 10, 'status': 'completed'},
            {'customer': 'Carlos Fernandez Diaz', 'service': 'recorte-barba', 'days_ago': 5, 'hour': 10, 'minute': 30, 'status': 'completed'},
            {'customer': 'Carlos Fernandez Diaz', 'service': 'corte-hombre', 'days_ago': 20, 'hour': 11, 'status': 'completed'},
            {'customer': 'Carlos Fernandez Diaz', 'service': 'recorte-barba', 'days_ago': 20, 'hour': 11, 'minute': 30, 'status': 'completed'},
            {'customer': 'Carlos Fernandez Diaz', 'service': 'afeitado-clasico', 'days_ago': 40, 'hour': 16, 'status': 'no_show'},

            # Laura — treatment client
            {'customer': 'Laura Sanchez Moreno', 'service': 'keratina', 'days_ago': 10, 'hour': 10, 'status': 'completed'},
            {'customer': 'Laura Sanchez Moreno', 'service': 'corte-mujer', 'days_ago': 30, 'hour': 12, 'status': 'completed'},
            {'customer': 'Laura Sanchez Moreno', 'service': 'hidratacion-profunda', 'days_ago': 30, 'hour': 13, 'status': 'completed'},
            {'customer': 'Laura Sanchez Moreno', 'service': 'keratina', 'days_ago': -3, 'hour': 10, 'status': 'pending'},

            # Pedro — new client
            {'customer': 'Pedro Gomez Torres', 'service': 'corte-hombre', 'days_ago': 2, 'hour': 15, 'status': 'completed'},

            # Sofia — color client with a cancellation
            {'customer': 'Sofia Rodriguez Navarro', 'service': 'mechas-completas', 'days_ago': 21, 'hour': 9, 'status': 'completed'},
            {'customer': 'Sofia Rodriguez Navarro', 'service': 'corte-mujer', 'days_ago': 21, 'hour': 11, 'status': 'completed'},
            {'customer': 'Sofia Rodriguez Navarro', 'service': 'mechas-parciales', 'days_ago': 8, 'hour': 10, 'status': 'cancelled'},
            {'customer': 'Sofia Rodriguez Navarro', 'service': 'mechas-parciales', 'days_ago': -2, 'hour': 10, 'status': 'confirmed'},
        ]

        staff_names = ['Lucia', 'Carmen', 'Javier']
        count = 0

        for i, item in enumerate(data):
            cust = customers.get(item['customer'])
            svc = services.get(item['service'])
            if not cust or not svc:
                continue

            start = today_9am - timedelta(days=item['days_ago'])
            start = start.replace(hour=item.get('hour', 10), minute=item.get('minute', 0))
            staff_name = staff_names[i % len(staff_names)]

            # Check if similar appointment already exists
            exists = Appointment.all_objects.filter(
                customer=cust,
                service_name=svc.name,
                start_datetime=start,
            ).exists()
            if exists:
                self.stdout.write(f'  Appointment: {cust.name} / {svc.name} [exists]')
                continue

            apt = Appointment(
                customer=cust,
                customer_name=cust.name,
                customer_phone=cust.phone,
                customer_email=cust.email,
                service_name=svc.name,
                service_price=svc.price,
                start_datetime=start,
                duration_minutes=svc.duration_minutes,
                status=item['status'],
                staff_name=staff_name,
                internal_notes='seed_salon',
            )
            if item['status'] == 'cancelled':
                apt.cancelled_at = start - timedelta(hours=2)
                apt.cancellation_reason = 'No pudo asistir'
            apt.save()
            count += 1
            self.stdout.write(f'  Appointment: {cust.name} / {svc.name} ({item["status"]}) [created]')

        self.stdout.write(f'  Total appointments created: {count}')
