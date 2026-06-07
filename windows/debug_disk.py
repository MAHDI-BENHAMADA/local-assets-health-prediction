import os
os.environ["PATH"] = r"C:\Program Files\smartmontools\bin" + os.pathsep + os.environ.get("PATH", "")

from pySMART import DeviceList

dev = DeviceList().devices[0]

print("=== diagnostics ===")
print(dev.diagnostics)
print()

print("=== attributes (non-None) ===")
for i, a in enumerate(dev.attributes or []):
    if a is not None:
        num  = getattr(a, "num",  "?")
        name = getattr(a, "name", "?")
        raw  = getattr(a, "raw",  "?")
        print(f"  [{i}] id={num} name={name} raw={raw}")
print()

print("=== raw dev fields ===")
for field in ["name", "model", "serial", "temperature", "assessment",
              "rotation_rate", "size", "interface", "smart_capable",
              "smart_enabled"]:
    print(f"  {field}: {getattr(dev, field, 'N/A')}")
