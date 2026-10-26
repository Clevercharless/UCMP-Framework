import inspect
import reporting.reporting_engine as reporting_module

ReportingEngine = reporting_module.ReportingEngine

print("=== CLASS FILE ===")
print(inspect.getfile(ReportingEngine))

print("\n=== METHOD OBJECT ===")
method = ReportingEngine.__dict__.get("_write_reports")
print(method)
print("Type:", type(method))

print("\n=== METHOD SIGNATURE ===")
print(inspect.signature(ReportingEngine._write_reports))

print("\n=== METHOD CODE LOCATION ===")
func = getattr(method, "__func__", method)
print("Code filename:", getattr(func, "__code__", None).co_filename
      if hasattr(func, "__code__") else "Unavailable")
print("First line:", getattr(func, "__code__", None).co_firstlineno
      if hasattr(func, "__code__") else "Unavailable")

print("\n=== SOURCE ===")
try:
    print(inspect.getsource(func))
except Exception as exc:
    print("Could not retrieve source:", repr(exc))

print("\n=== CLASS METHOD DEFINITIONS ===")
for name, member in ReportingEngine.__dict__.items():
    if "write_reports" in name or "resolve_reports" in name:
        print(name, repr(member))
