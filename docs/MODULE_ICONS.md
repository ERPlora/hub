# Module Icons System

ERPlora uses custom SVG and PNG icons for modules. Each module stores its icon in the `static/icons/` directory.

## Icon Location

Icons are stored within each module's static folder:

```
modules/
└── my_module/
    ├── module.py
    ├── static/
    │   └── icons/
    │       ├── icon.svg      # SVG icon (preferred)
    │       └── icon.png      # PNG icon (alternative)
    └── ...
```

## module.py Configuration

The `MODULE_ICON` field in `module.py` specifies the icon filename (relative to `static/icons/`):

```python
# modules/sales/module.py
from django.utils.translation import gettext_lazy as _

MODULE_ID = "sales"
MODULE_NAME = _("Sales")
MODULE_ICON = "icon.svg"  # Located at static/icons/icon.svg
MODULE_VERSION = "1.0.0"
MODULE_CATEGORY = "pos"

MENU = {
    "label": _("Sales"),
    "icon": "icon.svg",  # Same icon for menu
    "order": 20,
    "show": True,
}
```

### Icon Resolution

The system loads the icon from: `{module}/static/icons/{MODULE_ICON}`

- If `MODULE_ICON = "icon.svg"` → loads `sales/static/icons/icon.svg`
- If `MODULE_ICON = "icon.png"` → loads `sales/static/icons/icon.png`
- If not found → falls back to `cube-outline` (default Ionicon)

## Recommended Icon Source: React Icons

**Primary source for module icons**: [https://react-icons.github.io/react-icons/](https://react-icons.github.io/react-icons/)

React Icons provides access to multiple icon libraries in one place:
- **Ionicons 5** (io5) - Already used in ERPlora, consistent style
- **Heroicons** (hi, hi2) - Clean, modern design
- **Feather Icons** (fi) - Minimal, stroke-based
- **Phosphor Icons** (pi) - Flexible weights
- **Tabler Icons** (tb) - 4000+ icons, MIT license

### How to Download Icons from React Icons

1. Go to [react-icons.github.io/react-icons](https://react-icons.github.io/react-icons/)
2. Search for your icon (e.g., "cart", "inventory", "users")
3. Click on the icon to see its SVG code
4. Copy the SVG path data
5. Create your `icon.svg` file with the template below

### SVG Template for React Icons

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
  <!-- Paste path data from React Icons here -->
  <path d="..."/>
</svg>
```

For stroke-based icons (like Ionicons, Feather):
```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <!-- Paste path data here -->
  <path d="..."/>
</svg>
```

## Supported Formats

### SVG (Recommended)

- **Pros**: Scalable, small file size, CSS color inheritance
- **Format**: SVG 1.1 or 2.0
- **Size**: 24x24 pixels recommended (will scale via CSS)
- **Colors**: Use `currentColor` for inheriting text color
- **Clean**: Remove unnecessary metadata, comments, and IDs

### PNG (Alternative)

- **Pros**: Works with any design tool, no optimization needed
- **Size**: 48x48 or 64x64 pixels recommended (for retina displays)
- **Transparency**: Use transparent background
- **Note**: Embedded as base64, so keep file size under 10KB

## SVG Requirements

### Recommended SVG Template

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <!-- Your icon paths here -->
</svg>
```

### Color Inheritance

Use `currentColor` to inherit text color from parent:

```svg
<svg ... fill="currentColor">
  <path d="..."/>
</svg>
```

Or for stroked icons:

```svg
<svg ... stroke="currentColor" fill="none">
  <path d="..."/>
</svg>
```

## PNG Requirements

- **Dimensions**: 48x48 or 64x64 pixels (for retina)
- **Format**: PNG-24 with alpha transparency
- **Background**: Transparent
- **File size**: Under 10KB recommended
- **Color**: Use a single color that works on both light and dark backgrounds

## Using Icons in Templates

### Load the template tag

```django
{% load module_icons %}
```

### Render module icon

```django
{# Auto-loads SVG/PNG from module's static/icons/ #}
{% module_icon module_id="sales" css_class="text-primary" size="text-2xl" %}

{# From module metadata dict #}
{% module_icon_component module=module_data css_class="text-xl" %}
```

### Render SVG from path

```django
{% svg_icon path="sales/static/icons/icon.svg" css_class="w-6 h-6" %}
```

## Icon Sources

You can use icons from any source, as long as you have the license:

### Free Icon Libraries (SVG)

- **[React Icons](https://react-icons.github.io/react-icons/)** - Multiple libraries in one place
- **[Heroicons](https://heroicons.com/)** - MIT license, clean design
- **[Lucide](https://lucide.dev/)** - ISC license, fork of Feather
- **[Tabler Icons](https://tabler-icons.io/)** - MIT license, 4000+ icons
- **[Material Symbols](https://fonts.google.com/icons)** - Apache 2.0
- **[Phosphor Icons](https://phosphoricons.com/)** - MIT license
- **[Remix Icon](https://remixicon.com/)** - Apache 2.0
- **[Ionicons](https://ionic.io/ionicons)** - MIT license

## Best Practices

1. **Prefer SVG** - Better scaling, smaller size, CSS color support
2. **Consistent Style** - Use same stroke width and style across your module's icons
3. **Test at Small Sizes** - Icons should be recognizable at 16x16
4. **Use currentColor** - Allows CSS color inheritance (SVG only)
5. **Optimize Files** - Use SVGO for SVG, TinyPNG for PNG
6. **Square Format** - Use `viewBox="0 0 24 24"` for SVG consistency
7. **Keep PNG Small** - Under 10KB to avoid slow page loads

## SVGO Optimization

Install and run SVGO to optimize your SVGs:

```bash
npm install -g svgo

# Optimize a single file
svgo icon.svg -o icon.svg

# Optimize with config
svgo icon.svg --config svgo.config.js
```

Recommended SVGO config for module icons:

```js
// svgo.config.js
module.exports = {
  plugins: [
    'removeDoctype',
    'removeXMLProcInst',
    'removeComments',
    'removeMetadata',
    'removeEditorsNSData',
    'cleanupAttrs',
    'mergeStyles',
    'inlineStyles',
    'minifyStyles',
    'removeUselessDefs',
    'cleanupNumericValues',
    'convertColors',
    'removeUnknownsAndDefaults',
    'removeNonInheritableGroupAttrs',
    'removeUselessStrokeAndFill',
    'cleanupEnableBackground',
    'removeHiddenElems',
    'removeEmptyText',
    'convertShapeToPath',
    'moveElemsAttrsToGroup',
    'moveGroupAttrsToElems',
    'collapseGroups',
    'convertPathData',
    'convertTransform',
    'removeEmptyAttrs',
    'removeEmptyContainers',
    'mergePaths',
    'removeUnusedNS',
    'sortAttrs',
    'removeTitle',
    'removeDesc',
  ],
};
```

## PNG Optimization

Use online tools or CLI to optimize PNG files:

```bash
# Using pngquant (lossy, good compression)
pngquant --quality=65-80 icon.png -o icon.png

# Using optipng (lossless)
optipng -o7 icon.png
```

Or use online tools:
- [TinyPNG](https://tinypng.com/)
- [Squoosh](https://squoosh.app/)
