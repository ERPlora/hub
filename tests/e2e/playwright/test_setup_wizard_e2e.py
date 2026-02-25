"""
E2E test: Setup Wizard complete flow.

Runs against a LIVE Hub server at localhost:8000 with a FRESH database.
Tests the full flow: Cloud login → PIN setup → Setup wizard (4 steps) → Verify roles.

Prerequisites:
    1. Fresh DB (no users, no roles, StoreConfig.is_configured=False)
    2. Hub running: HUB_ENV=test python manage.py runserver
    3. Internet access (Cloud login calls erplora.com API)

Usage:
    HUB_ENV=test python -m pytest tests/e2e/playwright/test_setup_wizard_e2e.py -v -s
"""
import json
import os
import sqlite3
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

# Test against running dev server
BASE_URL = "http://localhost:8000"

# Demo credentials
DEMO_EMAIL = "demo@erplora.com"
DEMO_PASSWORD = "DemoPass123"
DEMO_PIN = "0000"

# DB path: detect from HUB_ENV
def _get_db_path():
    """Get the SQLite DB path based on HUB_ENV."""
    hub_env = os.environ.get('HUB_ENV', '')
    if hub_env == 'test':
        if sys.platform == 'darwin':
            return str(Path.home() / "Library" / "Application Support" / "ERPloraHubTest" / "db" / "db.sqlite3")
        else:
            return str(Path.home() / ".erplora-hub-test" / "db" / "db.sqlite3")
    else:
        if sys.platform == 'darwin':
            return str(Path.home() / "Library" / "Application Support" / "ERPloraHub" / "db" / "db.sqlite3")
        else:
            return str(Path.home() / ".erplora-hub" / "db" / "db.sqlite3")

DB_PATH = _get_db_path()


def _query_db(sql, params=()):
    """Execute a SQL query against the Hub SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(sql, params)
        return cursor.fetchall()
    finally:
        conn.close()


def test_full_setup_wizard_flow():
    """
    Complete E2E flow: Cloud login → PIN setup → Wizard (4 steps) → Verify DB.

    Single test function to ensure state carries across steps.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=50)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        context.set_default_timeout(20000)
        page = context.new_page()

        try:
            # ============================================================
            # STEP 1: Login page loads
            # ============================================================
            print("\n=== 1. Loading login page ===")
            page.goto(BASE_URL + "/login/")
            page.wait_for_timeout(1000)

            # Verify login page elements
            expect(page.locator("h1", has_text="ERPlora")).to_be_visible()
            print("  Login page loaded OK")

            # ============================================================
            # STEP 2: Cloud login
            # ============================================================
            print("\n=== 2. Cloud login ===")

            # Click Email tab (segment button)
            page.get_by_role("button", name="Email").click()
            page.wait_for_timeout(500)

            # Fill credentials
            page.locator("#cloud-email").fill(DEMO_EMAIL)
            page.locator("#cloud-password").fill(DEMO_PASSWORD)

            # Click Login button in the email form
            page.locator("button.color-primary:visible").click()

            # Wait for response — either PIN setup modal or redirect
            page.wait_for_timeout(5000)

            # ============================================================
            # STEP 3: PIN Setup
            # ============================================================
            print("\n=== 3. PIN setup ===")

            # Check if PIN setup modal appeared
            pin_modal = page.locator(".modal-title", has_text="Setup your PIN")
            if pin_modal.is_visible():
                print("  PIN setup modal visible")

                # Enter PIN first time: 0-0-0-0
                zero_key = page.locator(".modal .pinpad-grid .pinpad-key", has_text="0").last
                for _ in range(4):
                    zero_key.click()
                    page.wait_for_timeout(150)

                # Wait for confirm phase
                page.wait_for_timeout(800)
                print("  First PIN entered, confirming...")

                # Confirm PIN: 0-0-0-0
                for _ in range(4):
                    zero_key.click()
                    page.wait_for_timeout(150)

                # Wait for redirect after PIN setup
                page.wait_for_timeout(3000)
                print(f"  Current URL after PIN: {page.url}")
            else:
                print("  PIN setup modal not visible — user may already have PIN")

            # ============================================================
            # STEP 4: Setup Wizard - Step 1 (Regional)
            # ============================================================
            print("\n=== 4. Wizard Step 1: Regional ===")

            # Should be on setup wizard now (middleware redirects to /setup/)
            page.wait_for_timeout(2000)
            print(f"  Current URL: {page.url}")

            # If not on setup page, navigate there
            if "/setup" not in page.url:
                page.goto(BASE_URL + "/setup/")
                page.wait_for_timeout(2000)

            page.screenshot(path="/tmp/wizard_step1.png")

            # Step 1 has language/country/timezone — defaults are fine
            # The button says "Continue →"
            page.locator("button[type='submit']:visible").click()
            page.wait_for_timeout(2000)
            print("  Step 1 completed (defaults accepted)")

            # ============================================================
            # STEP 5: Setup Wizard - Step 2 (Modules/Blocks)
            # ============================================================
            print("\n=== 5. Wizard Step 2: Modules ===")

            # Wait for blocks to load from Cloud API
            page.wait_for_timeout(3000)
            page.screenshot(path="/tmp/wizard_step2_before.png")

            # Use the "Retail" quick start preset to select blocks
            # This clicks: applyPreset(['crm','pos','inventory','invoicing'])
            retail_chip = page.locator("button.chip", has_text="Retail")
            if retail_chip.count() > 0:
                retail_chip.click()
                page.wait_for_timeout(500)
                print("  Applied 'Retail' preset (crm, pos, inventory, invoicing)")
            else:
                # Fallback: click individual block cards by their h4 text
                print("  Retail preset not found, selecting blocks manually...")
                for block_name in ["CRM", "Point of Sale", "Inventory", "Invoicing"]:
                    card = page.locator(f".card:has(h4:has-text('{block_name}')):visible")
                    if card.count() > 0:
                        card.first.click()
                        page.wait_for_timeout(200)
                        print(f"    Selected: {block_name}")

            page.screenshot(path="/tmp/wizard_step2_after.png")

            # Click Continue (submit button)
            page.locator("button[type='submit']:visible").click()
            page.wait_for_timeout(5000)  # Step 2 save fetches roles from Cloud API
            print("  Step 2 completed")

            # ============================================================
            # STEP 6: Setup Wizard - Step 3 (Business)
            # ============================================================
            print("\n=== 6. Wizard Step 3: Business ===")
            page.screenshot(path="/tmp/wizard_step3.png")
            page.wait_for_timeout(500)

            # Fill business info
            biz_name = page.locator("#business_name:visible")
            if biz_name.count() > 0:
                biz_name.fill("Demo Business E2E")
                # business_address is a textarea
                page.locator("#business_address:visible").fill("Calle Test 123, Madrid")
                page.locator("#vat_number:visible").fill("B12345678")

                # Optional: email (phone uses Alpine component, skip it)
                email_input = page.locator("#email:visible")
                if email_input.count() > 0:
                    email_input.fill("demo@test.com")

                print("  Business info filled")
            else:
                print("  WARNING: business_name input not found")
                page.screenshot(path="/tmp/wizard_step3_debug.png")
                body_text = page.locator("body").inner_text()
                print(f"  Page text: {body_text[:500]}")

            # Click Continue (submit)
            page.locator("button[type='submit']:visible").click()
            page.wait_for_timeout(2000)
            print("  Step 3 completed")

            # ============================================================
            # STEP 7: Setup Wizard - Step 4 (Tax)
            # ============================================================
            print("\n=== 7. Wizard Step 4: Tax ===")
            page.screenshot(path="/tmp/wizard_step4.png")
            page.wait_for_timeout(500)

            # Tax rate should have default value 21
            tax_input = page.locator("#tax_rate:visible")
            if tax_input.count() > 0:
                current_val = tax_input.input_value()
                if not current_val:
                    tax_input.fill("21")
                print(f"  Tax rate: {tax_input.input_value()}")

            # Click "Complete Setup" (submit button)
            page.locator("button[type='submit']:visible").click()
            page.wait_for_timeout(5000)
            print(f"  Final URL: {page.url}")

            page.screenshot(path="/tmp/wizard_complete.png")

            # ============================================================
            # STEP 8: Verify database state (direct SQLite queries)
            # ============================================================
            print("\n=== 8. Verifying database ===")

            # Check StoreConfig
            store_rows = _query_db("SELECT is_configured, business_name, vat_number, tax_rate FROM core_storeconfig WHERE id=1")
            assert len(store_rows) == 1, "StoreConfig should exist"
            store = store_rows[0]
            print(f"  is_configured: {store['is_configured']}")
            print(f"  business_name: {store['business_name']}")
            print(f"  vat_number: {store['vat_number']}")
            print(f"  tax_rate: {store['tax_rate']}")
            assert store['is_configured'] == 1, "Store should be configured after wizard"
            assert store['business_name'] == "Demo Business E2E", f"Business name mismatch: {store['business_name']}"

            # Check HubConfig
            hub_rows = _query_db("SELECT hub_id, selected_blocks, solution_slug FROM core_hubconfig WHERE id=1")
            assert len(hub_rows) == 1, "HubConfig should exist"
            hub = hub_rows[0]
            hub_id = hub['hub_id']
            selected_blocks = json.loads(hub['selected_blocks']) if hub['selected_blocks'] else []
            print(f"  hub_id: {hub_id}")
            print(f"  selected_blocks: {selected_blocks}")
            print(f"  solution_slug: {hub['solution_slug']}")
            assert hub_id, "hub_id should be set after wizard"
            assert len(selected_blocks) > 0, "Should have selected blocks"
            assert "crm" in selected_blocks, f"CRM should be in selected blocks: {selected_blocks}"
            assert "pos" in selected_blocks, f"POS should be in selected blocks: {selected_blocks}"

            # Check Roles
            default_roles = _query_db(
                "SELECT name, source FROM accounts_roles WHERE hub_id=? AND source='basic' AND is_deleted=0",
                (hub_id,)
            )
            solution_roles = _query_db(
                "SELECT name, source FROM accounts_roles WHERE hub_id=? AND source='solution' AND is_deleted=0",
                (hub_id,)
            )
            print(f"\n  Default roles ({len(default_roles)}): {[r['name'] for r in default_roles]}")
            print(f"  Solution roles ({len(solution_roles)}): {[r['name'] for r in solution_roles]}")
            assert len(default_roles) >= 4, f"Should have 4+ default roles, got {len(default_roles)}"
            assert len(solution_roles) > 0, f"Should have solution roles for blocks {selected_blocks}"

            # Check Permissions (may be 0 if HUB_ENV=test with empty modules dir)
            perm_rows = _query_db(
                "SELECT COUNT(*) as cnt FROM accounts_permissions WHERE hub_id=? AND is_deleted=0",
                (hub_id,)
            )
            perm_count = perm_rows[0]['cnt']
            print(f"  Permissions: {perm_count}")
            if os.environ.get('HUB_ENV') != 'test':
                assert perm_count > 0, f"Should have permissions synced, got {perm_count}"
            else:
                print("  (HUB_ENV=test: 0 permissions expected — no modules installed)")

            # Check LocalUser was created
            user_rows = _query_db("SELECT name, email FROM accounts_local_users WHERE is_deleted=0")
            print(f"  Users: {[(u['name'], u['email']) for u in user_rows]}")
            assert len(user_rows) >= 1, "At least one user should exist after login"

            print("\n  ALL ASSERTIONS PASSED!")

        finally:
            context.close()
            browser.close()
