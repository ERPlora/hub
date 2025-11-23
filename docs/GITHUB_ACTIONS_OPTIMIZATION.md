# GitHub Actions - Estrategia de Optimización de Minutos

## 🎯 Objetivo

Mantener el uso de GitHub Actions **dentro del límite gratuito de 2,000 minutos/mes**.

## 📊 Análisis de Costos

### Multiplicadores de GitHub Actions

| Plataforma | Multiplicador | Costo Real por Minuto |
|------------|---------------|----------------------|
| Linux      | 1x            | 1 minuto            |
| Windows    | 2x            | 2 minutos           |
| macOS      | **10x**       | **10 minutos**      |

### Antes de Optimizar

```
Build típico en develop (3 plataformas):
- Linux:   4 min × 1  = 4 minutos
- Windows: 4 min × 2  = 8 minutos
- macOS:   4 min × 10 = 40 minutos
-----------------------------------------
TOTAL por build:       52 minutos

Con 5 pushes/día a develop:
- 5 builds/día × 52 min = 260 min/día
- 260 min/día × 30 días = 7,800 min/mes
-----------------------------------------
¡SOBREPASA por 5,800 minutos! (390% del límite)
```

### Después de Optimizar

```
Build optimizado en develop (solo Linux + Windows):
- Linux:   2 min × 1  = 2 minutos  (con caché)
- Windows: 2 min × 2  = 4 minutos  (con caché)
-----------------------------------------
TOTAL por build:       6 minutos

Con 5 pushes/día a develop:
- 5 builds/día × 6 min = 30 min/día
- 30 min/día × 30 días = 900 min/mes
- Builds de docs evitados: -30%
- Builds duplicados cancelados: -20%
-----------------------------------------
Uso real estimado:      ~600 min/mes
Releases (staging/main): ~600 min/mes
-----------------------------------------
TOTAL MENSUAL:          1,200 min/mes ✅
Dentro del límite con buffer de 800 min
```

## 🚀 Optimizaciones Implementadas

### 1. Eliminar macOS de Builds de Develop (77% ahorro)

**Impacto:** Reduce 40 de 52 minutos por build (77%)

**Implementación:**
```yaml
# .github/workflows/build-executables.yml
strategy:
  matrix:
    # Solo Linux y Windows en develop
    # macOS solo en releases finales
    os: [ubuntu-latest, windows-latest]
```

**Justificación:**
- macOS es 10x más caro que Linux
- En develop solo necesitas verificar que compila
- macOS se construye en releases finales (staging/main)

---

### 2. Caché de Dependencias (50% reducción de tiempo)

**Impacto:** Reduce tiempo de build de 4 min a 2 min

**Implementación:**
```yaml
- name: Set up Python
  uses: actions/setup-python@v5
  with:
    python-version: '3.11'
    cache: 'pip'  # Caché automático de pip

- name: Cache uv dependencies
  uses: actions/cache@v4
  with:
    path: |
      .venv
      ~/.cache/uv
    key: ${{ runner.os }}-uv-${{ hashFiles('pyproject.toml') }}
    restore-keys: |
      ${{ runner.os }}-uv-
```

**Beneficios:**
- Primera ejecución: instala dependencias (~2 min)
- Ejecuciones siguientes: usa caché (~30 seg)
- Caché se invalida solo cuando cambia `pyproject.toml`

---

### 3. Ignorar Cambios en Documentación (30% menos builds)

**Impacto:** Evita ~30% de builds innecesarios

**Implementación:**
```yaml
on:
  push:
    branches: [develop]
    paths-ignore:
      - '**.md'           # Ignorar Markdown
      - 'docs/**'         # Ignorar documentación
      - '.github/**'      # Ignorar workflows
      - '!.github/workflows/build-executables.yml'
      - 'LICENSE'
      - '.gitignore'
      - 'CLAUDE.md'
```

**Casos de uso:**
- ✅ Cambias solo README.md → NO ejecuta build
- ✅ Actualizas docs/ → NO ejecuta build
- ✅ Modificas .github/workflows/release.yml → NO ejecuta build
- ❌ Cambias código Python → SÍ ejecuta build
- ❌ Cambias .github/workflows/build-executables.yml → SÍ ejecuta build

---

### 4. Cancelar Builds Duplicados (20% menos desperdicio)

**Impacto:** Elimina ~20% de builds duplicados/desperdiciados

**Implementación:**
```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

**Escenario:**
```
1. Push a develop → Build #1 inicia
2. Corriges typo, push otra vez → Build #2 inicia
   → Build #1 se cancela automáticamente ✅
3. Solo Build #2 se completa
```

**Beneficio:** Si haces múltiples pushes seguidos, solo el último build se ejecuta.

---

## 📈 Resumen de Ahorros

| Optimización | Ahorro | Acumulado |
|--------------|--------|-----------|
| Base (3 plataformas) | 0% | 52 min/build |
| 1. Eliminar macOS | 77% | 12 min/build |
| 2. Caché de deps | 50% | 6 min/build |
| 3. Paths ignore | 30% menos builds | ~4 builds/día |
| 4. Cancel duplicados | 20% menos builds | ~3 builds/día |
| **TOTAL** | **85% ahorro** | **~600 min/mes** |

---

## 🎛️ Configuración por Branch

### Develop (builds automáticos)
- **Plataformas:** Linux + Windows
- **Frecuencia:** En cada push (excepto docs)
- **Uso:** ~600 min/mes
- **Artefactos:** Ejecutables simples (tar.gz, zip)

### Staging (releases automáticos)
- **Plataformas:** Linux + Windows + macOS
- **Frecuencia:** En cada push a staging
- **Uso:** ~400 min/mes
- **Artefactos:** Instaladores nativos con `-rc` (AppImage, .exe, DMG)

### Main (releases manuales)
- **Plataformas:** Linux + Windows + macOS
- **Frecuencia:** Manual via workflow_dispatch
- **Uso:** ~200 min/mes
- **Artefactos:** Instaladores nativos finales (AppImage, .exe, DMG)

**Total estimado:** 600 + 400 + 200 = **1,200 min/mes** (60% del límite)

---

## 💡 Consejos Adicionales

### 1. Commits Agrupados
En lugar de hacer múltiples pushes pequeños, agrupa cambios relacionados:

```bash
# ❌ MAL - 3 builds
git commit -m "fix typo"
git push
git commit -m "update docs"
git push
git commit -m "add test"
git push

# ✅ BIEN - 1 build
git add .
git commit -m "fix: typo, update docs, add test"
git push
```

### 2. Desarrollo Local
Prueba localmente antes de hacer push:

```bash
# Ejecuta tests localmente
pytest

# Ejecuta build localmente
pyinstaller main.spec

# Solo haz push cuando todo funcione
git push origin develop
```

### 3. Pull Requests
Usa Pull Requests para cambios grandes:
- PR desde feature branch → NO ejecuta builds
- Solo al hacer merge → ejecuta 1 build

### 4. Monitoreo de Uso
Revisa tu uso mensual:
- GitHub.com → Settings → Billing → Actions usage
- Objetivo: mantenerse por debajo de 2,000 min/mes

---

## 📊 Métricas de Éxito

### Objetivos Mensuales
- ✅ Uso total: < 2,000 minutos/mes
- ✅ Uso en develop: < 800 min/mes
- ✅ Uso en staging: < 600 min/mes
- ✅ Uso en main: < 400 min/mes
- ✅ Buffer disponible: > 200 min/mes

### Señales de Alerta
- ⚠️ Uso > 1,500 min/mes a mitad de mes
- ⚠️ Más de 10 builds/día en develop
- ⚠️ Builds fallando constantemente (desperdicio)

---

## 🔧 Troubleshooting

### "Me quedo sin minutos a mitad de mes"

**Causas comunes:**
1. Demasiados pushes a develop
2. Builds fallando (desperdicio)
3. PRs generando builds duplicados

**Soluciones:**
1. Agrupa commits antes de push
2. Prueba localmente primero
3. Usa `[skip ci]` en commits de docs:
   ```bash
   git commit -m "docs: update README [skip ci]"
   ```

### "Quiero build de macOS en develop"

Si necesitas ocasionalmente probar en macOS:

```bash
# Opción 1: Ejecutar workflow manual
gh workflow run build-release.yml -f version=test -f create_release=false

# Opción 2: Temporalmente añadir macOS al workflow
# Recuerda revertirlo después para no gastar minutos
```

---

## 📚 Referencias

- [GitHub Actions pricing](https://docs.github.com/en/billing/managing-billing-for-github-actions/about-billing-for-github-actions)
- [Caching dependencies](https://docs.github.com/en/actions/using-workflows/caching-dependencies-to-speed-up-workflows)
- [Skipping workflow runs](https://docs.github.com/en/actions/managing-workflow-runs/skipping-workflow-runs)
- [Using concurrency](https://docs.github.com/en/actions/using-jobs/using-concurrency)

---

**Última actualización:** 2025-11-07
**Optimizaciones activas:** 4/4 ✅
**Ahorro estimado:** 85%
