# Customers — ERPlora hub-next module

Declarative (`manifest_kind: declarative`) hub-next module. Customer directory with
CRUD over a single `customers` entity (Tier 0/1: pure-SQL queries/commands + a Lit
Web Component). Ported from the legacy `m_customers` Python module.

> **Module id:** `customers` (canonical, no prefix). **Repo name:** `module-customers`.

## What it provides

| Kind | Name | Permission |
|------|------|-----------|
| query | `customers.list` | `customers.view` |
| query | `customers.get` | `customers.view` |
| query | `customers.stats` | `customers.view` |
| command | `customers.create` → emits `customers.created` | `customers.manage` |
| command | `customers.update` → emits `customers.updated` | `customers.manage` |
| command | `customers.delete` (soft-delete) → emits `customers.deleted` | `customers.manage` |

Navigation entry `customers` renders the `<erp-customers-list>` Web Component
(`dist/customers.esm.js`).

## Layout

```
module.json                      # manifest (technical contract only)
migrations/sqlite/001_init.sql   # schema (hub_id + soft-delete + audit per §2.5)
queries/*.sql                    # declarative reads (runtime injects :hub_id)
commands/*.sql                   # declarative writes (runtime injects :new_id, :current_user_id, :now)
schemas/list.json                # JSON Schema for query params
src/customers-list.js            # Lit Web Component source
dist/customers.esm.js            # built WC (CSP-safe, no eval)
```

## Notes

- The runtime auto-injects `hub_id` and the audit/system params; module SQL never
  trusts UI-supplied values for them.
- Marketplace classification (sectors, business types, pricing) lives in the Cloud
  vendor portal, **not** in `module.json` (ARQUITECTURA.md §2.4).
- Group/tag/timeline features from the legacy module are deferred to a later phase.

## Build

```bash
pnpm install
pnpm build   # produces dist/customers.esm.js
```
