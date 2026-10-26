import inspect
import reporting.reporting_engine as reporting_module

print("Module loaded from:")
print(reporting_module.__file__)

print("\nCurrent method signature:")
print(inspect.signature(reporting_module.ReportingEngine._write_reports))

print("\nCurrent method source:")
print(inspect.getsource(reporting_module.ReportingEngine._write_reports))
