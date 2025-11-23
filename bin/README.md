# FRP Binaries

This directory contains platform-specific FRP client binaries.

## Download

Download the latest FRP release from: https://github.com/fatedier/frp/releases

Extract the following files to this directory:

- **Windows**: `frpc.exe`
- **macOS**: `frpc` (chmod +x frpc)
- **Linux**: `frpc` (chmod +x frpc)

## For Development

For local development and testing, you can use mock FRP client or download the real binary.

## For Production (PyInstaller)

The FRP binaries are included in the PyInstaller build via the `datas` section in `main.spec`:

```python
datas=[
    ('bin/frpc.exe', 'bin'),  # Windows
    ('bin/frpc', 'bin'),      # macOS/Linux
    # ...
]
```

Ensure binaries are present before building the executable.
