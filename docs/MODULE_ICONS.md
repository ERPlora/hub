# Module Icons System

ERPlora supports custom SVG and PNG icons for modules, with Ionic icons as fallback.

## Icon Priority

When rendering a module icon, the system checks in this order:

1. **Local SVG** - `{module}/static/icons/icon.svg` (inline, preferred)
2. **Local PNG** - `{module}/static/icons/icon.png` (base64 embedded)
3. **Ionic icon** - From `module.json` → `icon` field
4. **Fallback** - `cube-outline`

## Directory Structure

```
modules/
└── my_module/
    ├── module.json
    ├── static/
    │   └── icons/
    │       ├── icon.svg      # Preferred (inline, scalable)
    │       └── icon.png      # Fallback (base64 embedded)
    └── ...
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
{# Auto-detects SVG/PNG or falls back to Ionic #}
{% module_icon module_id="sales" css_class="text-primary" size="text-2xl" %}

{# From module metadata dict #}
{% module_icon_component module=module_data css_class="text-xl" %}
```

### Render explicit Ionic icon (no file lookup)

```django
{% module_icon icon="cart-outline" css_class="text-primary" %}
```

### Render SVG from path

```django
{% svg_icon path="sales/static/icons/icon.svg" css_class="w-6 h-6" %}
```

## Icon Sources

You can use icons from any source, as long as you have the license:

### Free Icon Libraries (SVG)

- **[Heroicons](https://heroicons.com/)** - MIT license, clean design
- **[Lucide](https://lucide.dev/)** - ISC license, fork of Feather
- **[Tabler Icons](https://tabler-icons.io/)** - MIT license, 4000+ icons
- **[Material Symbols](https://fonts.google.com/icons)** - Apache 2.0
- **[Phosphor Icons](https://phosphoricons.com/)** - MIT license
- **[Remix Icon](https://remixicon.com/)** - Apache 2.0

### Ionic Icons (Fallback)

If no local icon is provided, the system uses Ionic icons. Browse available icons:
- https://ionic.io/ionicons

## module.json Icon Field

The `icon` field in module.json is used as fallback when no local icon exists:

```json
{
  "module_id": "sales",
  "name": "Sales & POS",
  "icon": "cart-outline",
  "menu": {
    "icon": "cart-outline"
  }
}
```

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
