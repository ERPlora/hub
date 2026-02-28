"""
Locust load test for ERPlora Hub.

Simulates POS users performing realistic workflows:
- Login with PIN
- Browse products in POS
- Navigate between modules (Sales, Inventory, Customers)
- Complete sales
- View sales history

Usage:
    # Start Hub first:
    cd hub && python manage.py runserver

    # Then run locust (10 users, from hub/ directory):
    locust -f tests/load/locustfile.py --host=http://localhost:8000 --users 10 --spawn-rate 2

    # Or open web UI:
    locust -f tests/load/locustfile.py --host=http://localhost:8000
    # Then visit http://localhost:8089

    # Headless (no web UI), run for 2 minutes:
    locust -f tests/load/locustfile.py --host=http://localhost:8000 \
           --users 10 --spawn-rate 2 --run-time 2m --headless

Notes:
    - Before running, ensure a test user exists with PIN 1234:
        python manage.py shell -c "
        from apps.accounts.models import LocalUser
        u = LocalUser.objects.first()
        u.set_pin('1234')
        u.save()
        print(f'User: {u.id} ({u.name})')
        "
"""
import os
import random

from locust import HttpUser, task, between, events


# ---------------------------------------------------------------------------
# Configuration — override via env vars
# ---------------------------------------------------------------------------
USER_PIN = os.getenv("LOCUST_PIN", "1234")
USER_ID = os.getenv("LOCUST_USER_ID", "")  # auto-detected if empty


class POSUser(HttpUser):
    """Simulates a POS cashier working throughout the day."""

    # Wait 1-3 seconds between actions (realistic human pace)
    wait_time = between(1, 3)

    def on_start(self):
        """Login with PIN at the start of the session."""
        self.products = []

        # Get login page (sets session cookie)
        self.client.get("/login/", name="/login/")

        # Get user list to find a user ID
        user_id = USER_ID
        if not user_id:
            resp = self.client.get("/api/v1/auth/users/", name="/api/users")
            if resp.status_code == 200:
                try:
                    users = resp.json()
                    if users:
                        user_id = str(users[0]["id"])
                except Exception:
                    pass

        if not user_id:
            print("[!] No user found for login")
            return

        # Login with PIN (verify-pin is @csrf_exempt, accepts UUID user_id)
        resp = self.client.post(
            "/verify-pin/",
            json={"user_id": user_id, "pin": USER_PIN},
            name="/verify-pin",
        )
        if resp.status_code == 200:
            try:
                data = resp.json()
                if not data.get("success"):
                    print(f"[!] Login failed: {data.get('error', 'unknown')}")
            except Exception:
                print(f"[!] Login response not JSON: {resp.text[:100]}")
        else:
            print(f"[!] Login HTTP {resp.status_code}")

        # Pre-fetch product list for POS tasks
        self._load_products()

    def _load_products(self):
        """Load available products for POS simulation."""
        resp = self.client.get(
            "/m/sales/pos/api/products/",
            name="/pos/api/products",
        )
        if resp.status_code == 200:
            try:
                data = resp.json()
                products = data.get("products", []) if isinstance(data, dict) else data
                self.products = products
            except Exception:
                pass

    # === POS Tasks (most frequent — 70% of activity) ===

    @task(10)
    def pos_view(self):
        """Open the POS screen (full page load)."""
        self.client.get("/m/sales/pos/", name="/pos/ [page]")

    @task(15)
    def pos_load_products(self):
        """Fetch products via POS API (JSON)."""
        self.client.get(
            "/m/sales/pos/api/products/",
            name="/pos/api/products",
        )

    @task(8)
    def pos_complete_sale(self):
        """Complete a sale with random products."""
        if not self.products:
            self._load_products()
            if not self.products:
                return

        # Build a cart with 1-5 random products
        items = []
        num_items = random.randint(1, min(5, len(self.products)))
        for p in random.sample(self.products, num_items):
            items.append({
                "product_id": p["id"],
                "product_name": p.get("name", ""),
                "product_sku": p.get("sku", ""),
                "quantity": random.randint(1, 3),
                "price": p.get("price", 0),
                "tax_rate": p.get("tax_rate", 0),
                "tax_class_name": p.get("tax_class_name", ""),
                "is_service": p.get("is_service", False),
            })

        payload = {
            "items": items,
            "amount_tendered": 9999.99,
        }

        self.client.post(
            "/m/sales/pos/api/complete-sale/",
            json=payload,
            name="/pos/api/complete-sale",
        )

    # === Navigation Tasks (20% of activity) ===

    @task(3)
    def view_dashboard(self):
        """Load the main dashboard."""
        self.client.get("/", name="/ [dashboard]")

    @task(3)
    def view_sales_dashboard(self):
        """Load sales dashboard."""
        self.client.get("/m/sales/", name="/sales/ [dashboard]")

    @task(2)
    def view_sales_history(self):
        """Load sales history page."""
        self.client.get("/m/sales/history/", name="/sales/history/")

    @task(2)
    def view_inventory(self):
        """Browse inventory products."""
        self.client.get("/m/inventory/products/", name="/inventory/products/")

    @task(2)
    def view_customers(self):
        """Browse customers list."""
        self.client.get("/m/customers/", name="/customers/")

    # === HTMX Partials (10% — simulates SPA navigation) ===

    @task(3)
    def htmx_pos(self):
        """HTMX request for POS (partial load)."""
        self.client.get(
            "/m/sales/pos/",
            headers={"HX-Request": "true"},
            name="/pos/ [htmx]",
        )

    @task(2)
    def htmx_sales_history(self):
        """HTMX request for sales history."""
        self.client.get(
            "/m/sales/history/",
            headers={"HX-Request": "true"},
            name="/sales/history/ [htmx]",
        )

    @task(2)
    def htmx_sidebar(self):
        """HTMX sidebar refresh."""
        self.client.get(
            "/htmx/sidebar/",
            headers={"HX-Request": "true"},
            name="/htmx/sidebar/",
        )

    @task(1)
    def health_check(self):
        """Health check endpoint."""
        self.client.get("/health/", name="/health/")


# ---------------------------------------------------------------------------
# Event hooks — print summary with resource usage
# ---------------------------------------------------------------------------

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Print resource usage summary when test ends."""
    try:
        import psutil
        process = psutil.Process()
        mem = process.memory_info()
        print("\n" + "=" * 60)
        print("LOCUST PROCESS RESOURCE USAGE")
        print(f"  RSS Memory: {mem.rss / 1024 / 1024:.1f} MB")
        print(f"  VMS Memory: {mem.vms / 1024 / 1024:.1f} MB")
        print(f"  CPU %: {process.cpu_percent():.1f}%")
        print("=" * 60)
    except ImportError:
        pass
