# Testing Guide - CPOS Hub

Guía para ejecutar tests en el Hub usando pytest.

---

## 🧪 Configuración de Tests

### Dependencias instaladas

- `pytest` - Framework de testing
- `pytest-django` - Plugin para Django
- `pytest-cov` - Coverage reports
- `faker` - Generación de datos fake para tests

### Estructura de tests

```
hub/
├── conftest.py                 # Fixtures globales
├── pytest.ini                  # Configuración pytest
└── apps/
    ├── core/tests/
    │   ├── __init__.py
    │   ├── test_models.py
    │   └── test_views.py
    ├── pos/tests/
    ├── products/tests/
    ├── sales/tests/
    ├── plugins/tests/
    ├── hardware/tests/
    └── sync/tests/
```

---

## 🚀 Ejecutar Tests

### Todos los tests

```bash
pytest
```

### Tests de una app específica

```bash
pytest apps/core/tests/
```

### Tests con verbose

```bash
pytest -v
```

### Tests por marker

```bash
# Solo tests unitarios
pytest -m unit

# Solo tests de core
pytest -m core

# Solo tests de POS
pytest -m pos
```

### Tests con coverage

```bash
# Coverage básico
pytest --cov=apps

# Coverage con reporte HTML
pytest --cov=apps --cov-report=html

# Ver reporte
open htmlcov/index.html
```

### Tests específicos

```bash
# Un archivo
pytest apps/core/tests/test_models.py

# Una clase
pytest apps/core/tests/test_models.py::TestCoreModels

# Un método
pytest apps/core/tests/test_models.py::TestCoreModels::test_placeholder
```

---

## 📋 Markers Disponibles

Markers configurados en `pytest.ini`:

- `@pytest.mark.unit` - Tests unitarios
- `@pytest.mark.integration` - Tests de integración
- `@pytest.mark.core` - Tests de core app
- `@pytest.mark.pos` - Tests de pos app
- `@pytest.mark.products` - Tests de products app
- `@pytest.mark.sales` - Tests de sales app
- `@pytest.mark.plugins` - Tests de plugins app
- `@pytest.mark.hardware` - Tests de hardware app
- `@pytest.mark.sync` - Tests de sync app
- `@pytest.mark.slow` - Tests lentos

### Ejemplo de uso

```python
import pytest

@pytest.mark.unit
@pytest.mark.core
class TestCoreModels:
    def test_something(self):
        assert True
```

---

## 🧹 Limpieza Automática de Tests

Los tests están configurados con **limpieza automática** para evitar que se creen directorios no deseados en el proyecto (como `C:/`, `home/testuser/`, etc.).

### Fixture de Limpieza

El archivo `conftest.py` incluye un fixture `cleanup_test_artifacts` con `autouse=True`:

```python
@pytest.fixture(autouse=True)
def cleanup_test_artifacts():
    """
    Automatically cleanup test artifacts after each test.
    This prevents test directories (C:/, /home/testuser/, etc.) from being created.
    """
    yield  # Run the test

    # Cleanup after test
    test_dirs = [
        'C:',
        'C:\\',
        Path('home/testuser'),
        Path('Users/testuser'),
    ]

    for test_dir in test_dirs:
        dir_path = Path(test_dir)
        if dir_path.exists():
            try:
                shutil.rmtree(dir_path)
            except Exception:
                pass  # Ignore errors during cleanup
```

### ¿Qué Limpia?

- Directorios `C:/` y `C:\` (creados por tests de Windows paths)
- Directorios `home/testuser/` (creados por tests de Linux paths)
- Directorios `Users/testuser/` (creados por tests de macOS paths)

### Funcionamiento

1. **Antes del test**: El fixture hace `yield` (espera)
2. **Durante el test**: El test se ejecuta normalmente
3. **Después del test**: El fixture limpia automáticamente los directorios

**Resultado**: Los tests se pueden ejecutar múltiples veces sin crear artifacts en el proyecto.

---

## 🔧 Fixtures Disponibles

Fixtures globales en `conftest.py`:

### `cleanup_test_artifacts` (autouse=True)
Limpia automáticamente directorios de test después de cada ejecución
```python
# Se ejecuta automáticamente, no necesita ser declarado
def test_something():
    # Test se ejecuta normalmente
    # Limpieza automática después del test
    pass
```

### `user`
Usuario estándar de Django para testing
```python
def test_something(user):
    assert user.username == 'testuser'
```

### `superuser`
Superuser de Django para testing
```python
def test_admin_access(superuser):
    assert superuser.is_superuser
```

### `api_client`
Django test client para requests
```python
def test_endpoint(api_client):
    response = api_client.get('/some-url/')
    assert response.status_code == 200
```

### `hub_config` (TODO)
Configuración del Hub (se implementará cuando exista el modelo)

---

## 📝 Escribir Tests - Best Practices

### Estructura de test (Given-When-Then)

```python
def test_something(self, db, user):
    """
    GIVEN: Contexto inicial
    WHEN: Acción que se ejecuta
    THEN: Resultado esperado
    """
    # Arrange (Given)
    expected_value = 'test'

    # Act (When)
    result = some_function(user)

    # Assert (Then)
    assert result == expected_value
```

### Tests de modelos

```python
@pytest.mark.unit
@pytest.mark.core
class TestHubConfigModel:

    def test_create_hub_config(self, db, user):
        """
        GIVEN: Un usuario válido
        WHEN: Se crea una configuración de hub
        THEN: Debe crearse correctamente con valores por defecto
        """
        from apps.core.models import HubConfig

        config = HubConfig.objects.create(
            name='Test Hub',
            owner=user
        )

        assert config.name == 'Test Hub'
        assert config.owner == user
        assert config.is_configured is False
```

### Tests de views

```python
@pytest.mark.unit
@pytest.mark.core
class TestSetupWizardView:

    def test_setup_wizard_renders(self, api_client):
        """
        GIVEN: Hub sin configurar
        WHEN: Se accede al wizard de setup
        THEN: Debe renderizar el template correcto
        """
        response = api_client.get('/setup/')

        assert response.status_code == 200
        assert 'setup_wizard.html' in [t.name for t in response.templates]
```

---

## 🎯 TDD Workflow

1. **Red**: Escribir test que falla
```bash
pytest apps/core/tests/test_models.py::TestHubConfigModel::test_create_hub_config
# FAILED - Model doesn't exist yet
```

2. **Green**: Implementar código mínimo para pasar
```python
# apps/core/models.py
class HubConfig(models.Model):
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    is_configured = models.BooleanField(default=False)
```

```bash
python manage.py makemigrations
python manage.py migrate
pytest apps/core/tests/test_models.py::TestHubConfigModel::test_create_hub_config
# PASSED
```

3. **Refactor**: Mejorar código manteniendo tests verdes

---

## 📊 Coverage Goals

- **Mínimo aceptable**: 80%
- **Objetivo**: 90%+

```bash
# Verificar coverage actual
pytest --cov=apps --cov-report=term-missing

# Generar reporte HTML
pytest --cov=apps --cov-report=html
```

---

## 🐛 Troubleshooting

### Tests fallan con "Database access not allowed"

Agregar marker `@pytest.mark.django_db` o usar fixture `db`:

```python
@pytest.mark.django_db
def test_something():
    # Test con acceso a DB
    pass

# O usar fixture
def test_something(db):
    # Test con acceso a DB
    pass
```

### ImportError en tests

Verificar que `DJANGO_SETTINGS_MODULE` esté configurado en `pytest.ini`:

```ini
[pytest]
DJANGO_SETTINGS_MODULE = config.settings
```

### Tests lentos

Usar `--reuse-db` para no recrear la DB en cada run:

```bash
pytest --reuse-db
```

---

## 📚 Recursos

- [Pytest Documentation](https://docs.pytest.org/)
- [pytest-django](https://pytest-django.readthedocs.io/)
- [Django Testing](https://docs.djangoproject.com/en/5.2/topics/testing/)

---

**Última actualización**: 2025-01-08
