

def test_dynamic_prefix_dependency_matches_static_notebook_suffix():
    from parser.dependency_extractor import DependencyExtractor
    from parser.magic_parser import MagicCommand

    extractor = DependencyExtractor(['PFL/Common/utils.py', 'PFL/report.py'])
    magic = [MagicCommand('run', '${workspace_prefix}/PFL/Common/utils', 0, 1)]
    deps = extractor.extract('PFL/report.py', magic, None)
    assert deps[0].resolved_target == 'PFL/Common/utils.py'
