```python
import sys
import importlib

PROJECT_PACKAGE = "reporting"

# Find all already-imported modules belonging to the package.
modules_to_reload = [
    name
    for name in sys.modules
    if name == PROJECT_PACKAGE or name.startswith(PROJECT_PACKAGE + ".")
]

# Reload submodules before parent packages.
modules_to_reload.sort(key=lambda name: name.count("."), reverse=True)

for name in modules_to_reload:
    module = sys.modules.get(name)
    if module is not None:
        try:
            importlib.reload(module)
            print(f"Reloaded: {name}")
        except Exception as exc:
            print(f"Failed: {name}: {exc}")

print("Reload complete.")
```
