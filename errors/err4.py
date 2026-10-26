=== CLASS FILE ===
/Workspace/Users/charless.binny@poonawallafincorp.com/UCMP-Framework/reporting/reporting_engine.py

=== METHOD OBJECT ===
<staticmethod(<function ReportingEngine._write_reports at 0x7f7a926d5e40>)>
Type: <class 'staticmethod'>

=== METHOD SIGNATURE ===
(self, output_dir, reports, context)

=== METHOD CODE LOCATION ===
Code filename: /Workspace/Users/charless.binny@poonawallafincorp.com/UCMP-Framework/reporting/reporting_engine.py
First line: 124

=== SOURCE ===
    def _resolve_reports_dir(self, context: PipelineContext) -> Path:
        configured = context.config["output"]["reports_dir"]
        path = Path(configured)
        if not path.is_absolute():
            path = _PROJECT_ROOT / path
        path.mkdir(parents=True, exist_ok=True)
        return path


=== CLASS METHOD DEFINITIONS ===
_resolve_reports_dir <function ReportingEngine._resolve_reports_dir at 0x7f7a926d5da0>
_write_reports <staticmethod(<function ReportingEngine._write_reports at 0x7f7a926d5e40>)>
