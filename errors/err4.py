import inspect
import reporting.reporting_engine as reporting_module

print("Module loaded from:")
print(reporting_module.__file__)

print("\nCurrent method signature:")
print(inspect.signature(reporting_module.ReportingEngine._write_reports))

print("\nCurrent method source:")
print(inspect.getsource(reporting_module.ReportingEngine._write_reports))



Module loaded from:
/Workspace/Users/charless.binny@poonawallafincorp.com/UCMP-Framework/reporting/reporting_engine.py

Current method signature:
(self, output_dir, reports, context)

Current method source:
    def _resolve_reports_dir(self, context: PipelineContext) -> Path:
        configured = context.config["output"]["reports_dir"]
        path = Path(configured)
        if not path.is_absolute():
            path = _PROJECT_ROOT / path
        path.mkdir(parents=True, exist_ok=True)
        return path

