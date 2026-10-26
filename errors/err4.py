import importlib
import reporting.reporting_engine as reporting_module

importlib.invalidate_caches()
importlib.reload(reporting_module)

print("Module:", reporting_module.__file__)
print(
    "Signature:",
    importlib.import_module("inspect").signature(
        reporting_module.ReportingEngine._write_reports
    )
)
