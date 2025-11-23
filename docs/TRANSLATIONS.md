# Translation System (i18n)

ERPlora Hub uses Django's built-in internationalization (i18n) system for multi-language support.

## Supported Languages

- **English** (default): `en`
- **Spanish**: `es`

## For Developers

### 1. Adding Translations to Templates

Use the `{% trans %}` template tag for simple strings:

```django
{% load i18n %}

<button>{% trans "Save" %}</button>
<span>{% trans "Welcome" %}</span>
```

Use `{% blocktrans %}` for strings with variables:

```django
{% blocktrans with name=user.name %}Hello {{ name }}{% endblocktrans %}
```

### 2. Adding Translations to Python Code

```python
from django.utils.translation import gettext as _

# Simple translation
message = _("Product created successfully")

# Translation with variables
from django.utils.translation import gettext as _
message = _("%(count)d products found") % {'count': total}
```

### 3. Generating Translation Files

After adding new `{% trans %}` tags or `_()` calls:

```bash
cd /Users/ioan/Desktop/code/cpos/hub

# Extract translatable strings to .po files
.venv/bin/python manage.py makemessages -l es --ignore=.venv

# For plugins
cd plugins/my_plugin
../../.venv/bin/python ../../manage.py makemessages -l es
```

### 4. Editing Translations

Edit the `.po` files manually:

**Hub translations:** `locale/es/LC_MESSAGES/django.po`

**Plugin translations:** `plugins/<plugin_name>/locale/es/LC_MESSAGES/django.po`

Example entry:
```po
msgid "Search..."
msgstr "Buscar..."
```

### 5. Compiling Translations

After editing `.po` files:

```bash
# Compile all translations
.venv/bin/python manage.py compilemessages --ignore=.venv
```

This generates `.mo` files that Django uses at runtime.

### 6. Testing Translations

Change language in settings:
```python
LANGUAGE_CODE = 'es'  # or 'en'
```

Or use the language selector in the UI.

## Translation Workflow

### For Core Hub Components

```bash
# 1. Add {% trans %} tags to templates
# 2. Extract strings
.venv/bin/python manage.py makemessages -l es --ignore=.venv

# 3. Edit locale/es/LC_MESSAGES/django.po
# 4. Compile
.venv/bin/python manage.py compilemessages --ignore=.venv

# 5. Test by changing LANGUAGE_CODE or using language selector
```

### For Plugins

Plugins should include their own translation files:

```
plugins/my_plugin/
├── locale/
│   ├── en/
│   │   └── LC_MESSAGES/
│   │       ├── django.po
│   │       └── django.mo
│   └── es/
│       └── LC_MESSAGES/
│           ├── django.po
│           └── django.mo
├── templates/
├── models.py
└── views.py
```

Generate translations for a plugin:

```bash
cd plugins/my_plugin
../../.venv/bin/python ../../manage.py makemessages -l es
../../.venv/bin/python ../../manage.py makemessages -l en
../../.venv/bin/python ../../manage.py compilemessages
```

## Common Translations

### Data Table Component

| English | Spanish |
|---------|---------|
| Search... | Buscar... |
| Import | Importar |
| Export | Exportar |
| New | Nuevo |
| Show: | Mostrar: |
| All | Todos |
| per page | por página |
| Showing | Mostrando |
| of | de |
| items | elementos |

### Common Actions

| English | Spanish |
|---------|---------|
| Save | Guardar |
| Cancel | Cancelar |
| Delete | Eliminar |
| Edit | Editar |
| Create | Crear |
| Update | Actualizar |
| Close | Cerrar |
| Back | Volver |
| Next | Siguiente |
| Previous | Anterior |

## Best Practices

1. **Always use English as the source language** in templates and code
2. **Keep strings short and context-independent**
3. **Use variables for dynamic content**: `{% blocktrans with name=user.name %}`
4. **Don't concatenate translated strings** - use one full string instead
5. **Test translations** before committing
6. **Document new translatable strings** in plugin documentation

## Auto-Generated Files

- `locale/es/LC_MESSAGES/django.mo` - Compiled translations (binary)
- `plugins/*/locale/*/LC_MESSAGES/django.mo` - Plugin compiled translations

⚠️ **Do not edit `.mo` files manually** - they are auto-generated from `.po` files.

## Troubleshooting

### Translations not showing

1. Check that `.mo` files exist (run `compilemessages`)
2. Verify `LANGUAGE_CODE` in settings
3. Clear browser cache
4. Restart development server

### New strings not extracted

1. Ensure `{% load i18n %}` is at the top of templates
2. Use correct syntax: `{% trans "string" %}` not `{% trans string %}`
3. Run `makemessages` with correct locale

### Fuzzy translations

If Django marks translations as "fuzzy":
```po
#, fuzzy
msgid "Hello"
msgstr "Hola"
```

Remove the `#, fuzzy` line and recompile.

---

**Last updated:** 2025-01-22
