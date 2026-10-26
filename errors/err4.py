import inspect
import reporting.reporting_engine as reporting_module

cls = reporting_module.ReportingEngine

print("Module:", reporting_module.__file__)
print("Method signature:", inspect.signature(cls._write_reports))
print("Is static method:", isinstance(cls.__dict__["_write_reports"], staticmethod))

print("\nActual method implementation:")
print(inspect.unwrap(cls._write_reports).__code__.co_firstlineno)
print(inspect.getsource(inspect.unwrap(cls._write_reports)))
