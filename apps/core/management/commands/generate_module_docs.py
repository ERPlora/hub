"""
Generate README.md for each module automatically.

Reads module.py, models.py, urls.py, ai_tools.py, and apps.py to build
comprehensive documentation for each module.

Usage:
    python manage.py generate_module_docs              # All modules
    python manage.py generate_module_docs inventory     # Single module
    python manage.py generate_module_docs --dry-run     # Preview without writing
"""

import ast
import importlib
import inspect
import os
import re
import sys
import textwrap
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import models


class Command(BaseCommand):
    help = 'Generate README.md documentation for modules'

    def add_arguments(self, parser):
        parser.add_argument(
            'module_ids',
            nargs='*',
            help='Module IDs to document (default: all)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print output without writing files',
        )

    def handle(self, *args, **options):
        modules_dir = Path(settings.MODULES_DIR)

        if not modules_dir.exists():
            raise CommandError(f"Modules directory not found: {modules_dir}")

        # Get module list
        if options['module_ids']:
            module_ids = options['module_ids']
        else:
            module_ids = sorted([
                d.name for d in modules_dir.iterdir()
                if d.is_dir() and not d.name.startswith(('_', '.'))
                and (d / 'module.py').exists()
            ])

        generated = 0
        for module_id in module_ids:
            module_dir = modules_dir / module_id
            if not module_dir.exists():
                self.stderr.write(f"Module not found: {module_id}")
                continue

            try:
                readme = self._generate_readme(module_id, module_dir)

                if options['dry_run']:
                    self.stdout.write(f"\n{'='*60}")
                    self.stdout.write(f"  {module_id}/README.md")
                    self.stdout.write(f"{'='*60}\n")
                    self.stdout.write(readme)
                else:
                    (module_dir / 'README.md').write_text(readme)
                    self.stdout.write(self.style.SUCCESS(f"  {module_id}/README.md"))

                generated += 1
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"  {module_id}: {e}"))

        self.stdout.write(f"\nGenerated {generated}/{len(module_ids)} READMEs")

    def _generate_readme(self, module_id, module_dir):
        """Generate full README content for a module."""
        sections = []

        # Parse module.py
        meta = self._parse_module_py(module_dir / 'module.py')

        # Header
        icon = meta.get('MODULE_ICON', '')
        name = meta.get('MODULE_NAME', module_id.replace('_', ' ').title())
        sections.append(f"# {name}\n")

        # Overview table
        sections.append(self._section_overview(module_id, meta))

        # Dependencies
        if meta.get('DEPENDENCIES'):
            sections.append(self._section_dependencies(meta))

        # Models
        models_info = self._parse_models(module_id, module_dir / 'models.py')
        if models_info:
            sections.append(self._section_models(models_info))

        # Cross-module relationships
        relationships = self._find_relationships(models_info)
        if relationships:
            sections.append(self._section_relationships(relationships))

        # URL endpoints
        urls_info = self._parse_urls(module_dir / 'urls.py')
        if urls_info:
            sections.append(self._section_urls(module_id, urls_info))

        # Permissions
        if meta.get('PERMISSIONS'):
            sections.append(self._section_permissions(meta))

        # Navigation
        if meta.get('NAVIGATION'):
            sections.append(self._section_navigation(meta))

        # AI Tools
        ai_tools = self._parse_ai_tools(module_dir / 'ai_tools.py')
        if ai_tools:
            sections.append(self._section_ai_tools(ai_tools))

        # Hooks (registered and consumed)
        hooks_info = self._find_hooks(module_id, module_dir)
        if hooks_info:
            sections.append(self._section_hooks(hooks_info))

        # Signals
        signals_info = self._find_signals(module_id, module_dir)
        if signals_info:
            sections.append(self._section_signals(signals_info))

        # Files
        sections.append(self._section_file_structure(module_dir))

        return '\n'.join(sections)

    # =========================================================================
    # PARSERS
    # =========================================================================

    def _parse_module_py(self, path):
        """Parse module.py using AST to extract metadata."""
        if not path.exists():
            return {}

        source = path.read_text()
        tree = ast.parse(source)

        meta = {}
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        key = target.id
                        value = self._ast_to_value(node.value)
                        if value is not None:
                            meta[key] = value

        return meta

    def _ast_to_value(self, node):
        """Convert AST node to Python value."""
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.List):
            return [self._ast_to_value(el) for el in node.elts]
        elif isinstance(node, ast.Dict):
            result = {}
            for k, v in zip(node.keys, node.values):
                key = self._ast_to_value(k)
                val = self._ast_to_value(v)
                if key is not None:
                    result[key] = val
            return result
        elif isinstance(node, ast.Call):
            # Handle _('string') translation calls
            if node.args:
                return self._ast_to_value(node.args[0])
        elif isinstance(node, ast.Name):
            if node.id in ('True', 'False', 'None'):
                return {'True': True, 'False': False, 'None': None}[node.id]
        return None

    def _parse_models(self, module_id, path):
        """Parse models.py to extract model information."""
        if not path.exists():
            return []

        # Try to get models from Django's registry
        models_info = []

        try:
            app_config = apps.get_app_config(module_id)
            for model in app_config.get_models():
                info = self._extract_model_info(model)
                models_info.append(info)
        except LookupError:
            # App not in registry, parse AST as fallback
            models_info = self._parse_models_ast(path)

        return models_info

    def _extract_model_info(self, model):
        """Extract model info from a Django model class."""
        info = {
            'name': model.__name__,
            'doc': (model.__doc__ or '').strip(),
            'db_table': model._meta.db_table,
            'fields': [],
            'methods': [],
            'properties': [],
            'meta': {},
            'fk_references': [],
        }

        # Fields
        for field in model._meta.get_fields():
            if hasattr(field, 'column') or isinstance(field, models.ManyToManyField):
                field_info = {
                    'name': field.name,
                    'type': type(field).__name__,
                }

                if isinstance(field, (models.ForeignKey, models.OneToOneField)):
                    related = field.related_model
                    if related is not None:
                        field_info['related_model'] = f"{related._meta.app_label}.{related.__name__}"
                    else:
                        field_info['related_model'] = '(unresolved)'
                    field_info['on_delete'] = self._get_on_delete_name(field)
                    field_info['null'] = field.null
                    info['fk_references'].append(field_info)
                elif isinstance(field, models.ManyToManyField):
                    related = field.related_model
                    if related is not None:
                        field_info['related_model'] = f"{related._meta.app_label}.{related.__name__}"
                    else:
                        field_info['related_model'] = '(unresolved)'
                elif hasattr(field, 'max_length') and field.max_length:
                    field_info['max_length'] = field.max_length

                if hasattr(field, 'choices') and field.choices:
                    field_info['choices'] = [
                        (str(v), str(l)) for v, l in field.choices
                    ]

                field_info['required'] = not getattr(field, 'blank', True)

                info['fields'].append(field_info)

        # Django auto-generated exception classes and internal attrs to skip
        _skip_names = {
            'DoesNotExist', 'MultipleObjectsReturned', 'NotUpdated',
            'Meta', 'objects', 'all_objects',
        }

        # Methods and properties (from model's own __dict__ only)
        for name, attr in model.__dict__.items():
            if name.startswith('_') or name in _skip_names:
                continue

            try:
                # Skip Django TextChoices/IntegerChoices inner classes
                if isinstance(attr, type) and issubclass(attr, (models.TextChoices, models.IntegerChoices)):
                    continue

                if isinstance(attr, property):
                    doc = (attr.fget.__doc__ or '').strip() if attr.fget else ''
                    info['properties'].append({'name': name, 'doc': doc})
                elif isinstance(attr, classmethod):
                    func = attr.__func__
                    doc = (func.__doc__ or '').strip()
                    info['methods'].append({'name': name, 'doc': doc})
                elif callable(attr) and name not in (
                    'save', 'delete', 'clean', 'full_clean', 'validate_unique',
                    'from_db', 'refresh_from_db', 'serializable_value',
                ):
                    doc = (attr.__doc__ or '').strip() if hasattr(attr, '__doc__') else ''
                    info['methods'].append({'name': name, 'doc': doc})
            except Exception:
                continue

        # Meta
        meta = model._meta
        if meta.ordering:
            info['meta']['ordering'] = list(meta.ordering)
        if meta.verbose_name != meta.model_name:
            info['meta']['verbose_name'] = str(meta.verbose_name)
        if meta.unique_together:
            info['meta']['unique_together'] = [list(ut) for ut in meta.unique_together]

        return info

    def _get_on_delete_name(self, field):
        """Get string name of on_delete behavior."""
        if not hasattr(field, 'remote_field') or field.remote_field is None:
            return '?'
        on_delete = field.remote_field.on_delete
        mapping = {
            models.CASCADE: 'CASCADE',
            models.PROTECT: 'PROTECT',
            models.SET_NULL: 'SET_NULL',
            models.SET_DEFAULT: 'SET_DEFAULT',
            models.DO_NOTHING: 'DO_NOTHING',
        }
        return mapping.get(on_delete, 'SET')

    def _parse_models_ast(self, path):
        """Fallback: parse models from AST when app isn't registered."""
        source = path.read_text()
        tree = ast.parse(source)

        models_info = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                # Check if it inherits from a model base
                bases = [self._ast_to_value(b) or ast.dump(b) for b in node.bases]
                is_model = any(
                    'Model' in str(b) or 'HubBaseModel' in str(b) or 'TimeStamped' in str(b)
                    for b in bases
                )
                if is_model:
                    doc = ast.get_docstring(node) or ''
                    models_info.append({
                        'name': node.name,
                        'doc': doc.strip(),
                        'fields': [],
                        'methods': [],
                        'properties': [],
                        'meta': {},
                        'fk_references': [],
                    })

        return models_info

    def _parse_urls(self, path):
        """Parse urls.py to extract URL patterns."""
        if not path.exists():
            return []

        source = path.read_text()
        urls = []

        # Match path('pattern', view, name='name')
        pattern = re.compile(
            r"path\(\s*['\"]([^'\"]*)['\"]"
            r".*?"
            r"name=['\"]([^'\"]+)['\"]",
            re.DOTALL,
        )

        for match in pattern.finditer(source):
            url_path = match.group(1)
            name = match.group(2)

            # Try to find the view function name
            full_match = match.group(0)
            view_match = re.search(r'views?\.(\w+)', full_match)
            view_name = view_match.group(1) if view_match else ''

            # Determine HTTP method from view name or decorator context
            method = 'GET'
            if any(w in name for w in ('save', 'create', 'add', 'delete', 'update', 'import', 'bulk')):
                method = 'GET/POST'

            urls.append({
                'path': url_path,
                'name': name,
                'view': view_name,
                'method': method,
            })

        return urls

    def _parse_ai_tools(self, path):
        """Parse ai_tools.py to extract tool definitions."""
        if not path.exists():
            return []

        source = path.read_text()
        tree = ast.parse(source)

        tools = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                tool = {'name': '', 'description': '', 'parameters': []}

                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name):
                                val = self._ast_to_value(item.value)
                                if target.id == 'name' and val:
                                    tool['name'] = val
                                elif target.id == 'description' and val:
                                    tool['description'] = val
                                elif target.id == 'parameters' and isinstance(val, dict):
                                    props = val.get('properties', {})
                                    required = val.get('required', [])
                                    for pname, pinfo in props.items():
                                        if isinstance(pinfo, dict):
                                            tool['parameters'].append({
                                                'name': pname,
                                                'type': pinfo.get('type', 'string'),
                                                'description': pinfo.get('description', ''),
                                                'required': pname in required,
                                            })

                if tool['name']:
                    tools.append(tool)

        return tools

    def _find_hooks(self, module_id, module_dir):
        """Find hook registrations and emissions in module files."""
        hooks = {'registers': [], 'emits': []}

        for py_file in module_dir.glob('**/*.py'):
            try:
                source = py_file.read_text()
            except Exception:
                continue

            # Find hook registrations: hooks.add_action('name', ...) or hooks.add_filter('name', ...)
            for match in re.finditer(r"hooks\.add_(action|filter)\(\s*['\"]([^'\"]+)['\"]", source):
                hooks['registers'].append({
                    'type': match.group(1),
                    'hook': match.group(2),
                    'file': py_file.name,
                })

            # Find hook emissions: hooks.do_action('name', ...) or hooks.apply_filters('name', ...)
            for match in re.finditer(r"hooks\.(do_action|apply_filters)\(\s*['\"]([^'\"]+)['\"]", source):
                hooks['emits'].append({
                    'type': 'action' if 'do_action' in match.group(1) else 'filter',
                    'hook': match.group(2),
                    'file': py_file.name,
                })

        return hooks if hooks['registers'] or hooks['emits'] else None

    def _find_signals(self, module_id, module_dir):
        """Find signal emissions and receivers in module files."""
        signals = {'emits': [], 'receives': []}

        for py_file in module_dir.glob('**/*.py'):
            try:
                source = py_file.read_text()
            except Exception:
                continue

            # Find signal emissions: signal_name.send(sender=...)
            for match in re.finditer(r"(\w+)\.send\(\s*sender=", source):
                signal_name = match.group(1)
                if signal_name not in ('self', 'cls'):
                    signals['emits'].append({
                        'signal': signal_name,
                        'file': py_file.name,
                    })

            # Find signal receivers: @receiver(signal_name)
            for match in re.finditer(r"@receiver\(\s*(\w+)", source):
                signals['receives'].append({
                    'signal': match.group(1),
                    'file': py_file.name,
                })

        return signals if signals['emits'] or signals['receives'] else None

    def _find_relationships(self, models_info):
        """Extract cross-module FK relationships from model info."""
        relationships = []
        for model_info in models_info:
            for fk in model_info.get('fk_references', []):
                related = fk.get('related_model', '')
                # Only cross-module references (different app_label)
                if '.' in related:
                    app_label = related.split('.')[0]
                    model_app = model_info['name']
                    relationships.append({
                        'from_model': model_info['name'],
                        'field': fk['name'],
                        'to': related,
                        'on_delete': fk.get('on_delete', '?'),
                        'nullable': fk.get('null', False),
                    })
        return relationships

    # =========================================================================
    # SECTION GENERATORS
    # =========================================================================

    def _section_overview(self, module_id, meta):
        """Generate overview section."""
        lines = ['## Overview\n']
        lines.append(f"| Property | Value |")
        lines.append(f"|----------|-------|")
        lines.append(f"| **Module ID** | `{module_id}` |")
        lines.append(f"| **Version** | `{meta.get('MODULE_VERSION', '1.0.0')}` |")

        icon = meta.get('MODULE_ICON', '')
        if icon:
            lines.append(f"| **Icon** | `{icon}` |")

        deps = meta.get('DEPENDENCIES', [])
        if deps:
            lines.append(f"| **Dependencies** | {', '.join(f'`{d}`' for d in deps)} |")
        else:
            lines.append(f"| **Dependencies** | None |")

        lines.append('')
        return '\n'.join(lines)

    def _section_dependencies(self, meta):
        """Generate dependencies section."""
        deps = meta.get('DEPENDENCIES', [])
        lines = ['## Dependencies\n']
        lines.append('This module requires the following modules to be installed:\n')
        for dep in deps:
            lines.append(f"- `{dep}`")
        lines.append('')
        return '\n'.join(lines)

    def _section_models(self, models_info):
        """Generate models section."""
        lines = ['## Models\n']

        for model in models_info:
            lines.append(f"### `{model['name']}`\n")

            if model.get('doc'):
                lines.append(f"{model['doc']}\n")

            # Fields table
            fields = [f for f in model.get('fields', [])
                       if f['name'] not in ('id', 'hub_id', 'created_at', 'updated_at',
                                             'created_by', 'updated_by', 'is_deleted', 'deleted_at')]
            if fields:
                lines.append('| Field | Type | Details |')
                lines.append('|-------|------|---------|')
                for f in fields:
                    details = []
                    if f.get('related_model'):
                        details.append(f"→ `{f['related_model']}`")
                    if f.get('on_delete'):
                        details.append(f"on_delete={f['on_delete']}")
                    if f.get('max_length'):
                        details.append(f"max_length={f['max_length']}")
                    if f.get('choices'):
                        choice_vals = ', '.join(c[0] for c in f['choices'][:6])
                        if len(f['choices']) > 6:
                            choice_vals += ', ...'
                        details.append(f"choices: {choice_vals}")
                    if f.get('null') or not f.get('required'):
                        details.append('optional')

                    detail_str = ', '.join(details) if details else ''
                    lines.append(f"| `{f['name']}` | {f['type']} | {detail_str} |")
                lines.append('')

            # Methods
            methods = model.get('methods', [])
            if methods:
                lines.append('**Methods:**\n')
                for m in methods:
                    doc = f" — {m['doc']}" if m.get('doc') else ''
                    lines.append(f"- `{m['name']}()`{doc}")
                lines.append('')

            # Properties
            props = model.get('properties', [])
            if props:
                lines.append('**Properties:**\n')
                for p in props:
                    doc = f" — {p['doc']}" if p.get('doc') else ''
                    lines.append(f"- `{p['name']}`{doc}")
                lines.append('')

        return '\n'.join(lines)

    def _section_relationships(self, relationships):
        """Generate cross-module relationships section."""
        lines = ['## Cross-Module Relationships\n']
        lines.append('| From | Field | To | on_delete | Nullable |')
        lines.append('|------|-------|----|-----------|----------|')
        for rel in relationships:
            nullable = 'Yes' if rel['nullable'] else 'No'
            lines.append(
                f"| `{rel['from_model']}` | `{rel['field']}` | "
                f"`{rel['to']}` | {rel['on_delete']} | {nullable} |"
            )
        lines.append('')
        return '\n'.join(lines)

    def _section_urls(self, module_id, urls_info):
        """Generate URL endpoints section."""
        lines = ['## URL Endpoints\n']
        lines.append(f"Base path: `/m/{module_id}/`\n")
        lines.append('| Path | Name | Method |')
        lines.append('|------|------|--------|')
        for url in urls_info:
            full_path = url['path'] if url['path'] else '(root)'
            lines.append(f"| `{full_path}` | `{url['name']}` | {url['method']} |")
        lines.append('')
        return '\n'.join(lines)

    def _section_permissions(self, meta):
        """Generate permissions section."""
        lines = ['## Permissions\n']

        perms = [p for p in meta.get('PERMISSIONS', []) if p]
        lines.append('| Permission | Description |')
        lines.append('|------------|-------------|')
        for perm in perms:
            # Convert permission string to readable description
            parts = perm.rsplit('.', 1)
            desc = parts[-1].replace('_', ' ').title() if len(parts) > 1 else perm
            lines.append(f"| `{perm}` | {desc} |")
        lines.append('')

        # Role permissions
        roles = meta.get('ROLE_PERMISSIONS', {})
        if roles:
            lines.append('**Role assignments:**\n')
            for role, perms_list in roles.items():
                if perms_list == ['*']:
                    lines.append(f"- **{role}**: All permissions")
                else:
                    perm_str = ', '.join(f'`{p}`' for p in perms_list[:8])
                    if len(perms_list) > 8:
                        perm_str += f' (+{len(perms_list) - 8} more)'
                    lines.append(f"- **{role}**: {perm_str}")
            lines.append('')

        return '\n'.join(lines)

    def _section_navigation(self, meta):
        """Generate navigation section."""
        nav = meta.get('NAVIGATION', [])
        if not nav:
            return ''

        lines = ['## Navigation\n']
        lines.append('| View | Icon | ID | Fullpage |')
        lines.append('|------|------|----|----------|')
        for item in nav:
            if isinstance(item, dict):
                label = item.get('label', '')
                icon = item.get('icon', '')
                view_id = item.get('id', '')
                fullpage = 'Yes' if item.get('fullpage') else 'No'
                lines.append(f"| {label} | `{icon}` | `{view_id}` | {fullpage} |")
        lines.append('')
        return '\n'.join(lines)

    def _section_ai_tools(self, tools):
        """Generate AI tools section."""
        lines = ['## AI Tools\n']
        lines.append('Tools available for the AI assistant:\n')

        for tool in tools:
            lines.append(f"### `{tool['name']}`\n")
            if tool.get('description'):
                lines.append(f"{tool['description']}\n")

            if tool.get('parameters'):
                lines.append('| Parameter | Type | Required | Description |')
                lines.append('|-----------|------|----------|-------------|')
                for p in tool['parameters']:
                    req = 'Yes' if p.get('required') else 'No'
                    lines.append(
                        f"| `{p['name']}` | {p.get('type', 'string')} | "
                        f"{req} | {p.get('description', '')} |"
                    )
                lines.append('')

        return '\n'.join(lines)

    def _section_hooks(self, hooks_info):
        """Generate hooks section."""
        lines = ['## Hooks\n']

        if hooks_info.get('emits'):
            lines.append('**Emits (other modules can listen):**\n')
            seen = set()
            for h in hooks_info['emits']:
                key = f"{h['type']}:{h['hook']}"
                if key not in seen:
                    seen.add(key)
                    lines.append(f"- `{h['hook']}` ({h['type']}) — in `{h['file']}`")
            lines.append('')

        if hooks_info.get('registers'):
            lines.append('**Listens to (hooks from other modules):**\n')
            seen = set()
            for h in hooks_info['registers']:
                key = f"{h['type']}:{h['hook']}"
                if key not in seen:
                    seen.add(key)
                    lines.append(f"- `{h['hook']}` ({h['type']}) — in `{h['file']}`")
            lines.append('')

        return '\n'.join(lines)

    def _section_signals(self, signals_info):
        """Generate signals section."""
        lines = ['## Signals\n']

        if signals_info.get('emits'):
            lines.append('**Emits:**\n')
            seen = set()
            for s in signals_info['emits']:
                if s['signal'] not in seen:
                    seen.add(s['signal'])
                    lines.append(f"- `{s['signal']}` — in `{s['file']}`")
            lines.append('')

        if signals_info.get('receives'):
            lines.append('**Receives:**\n')
            seen = set()
            for s in signals_info['receives']:
                if s['signal'] not in seen:
                    seen.add(s['signal'])
                    lines.append(f"- `{s['signal']}` — in `{s['file']}`")
            lines.append('')

        return '\n'.join(lines)

    def _section_file_structure(self, module_dir):
        """Generate file structure section."""
        lines = ['## File Structure\n', '```']

        for item in sorted(module_dir.rglob('*')):
            if any(part.startswith(('.', '__pycache__')) for part in item.parts):
                continue
            if item.suffix in ('.pyc', '.mo'):
                continue

            rel = item.relative_to(module_dir)
            depth = len(rel.parts) - 1

            # Skip individual migration files (just show the directory)
            if 'migrations' in rel.parts and depth > 1:
                continue

            # Skip individual SVG icon files (just show the directory)
            if item.suffix == '.svg' and 'ion' in rel.parts:
                continue

            # Skip individual locale .po files deeper than lang level
            if item.suffix == '.po' and depth > 3:
                continue

            prefix = '  ' * depth
            name = item.name
            if item.is_dir():
                name += '/'
            lines.append(f"{prefix}{name}")

        lines.append('```\n')
        return '\n'.join(lines)
