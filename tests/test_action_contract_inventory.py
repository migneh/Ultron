"""Check all bundled declarations without importing optional native dependencies."""
import ast
from pathlib import Path
from types import SimpleNamespace

from ultron.core.action_loader import _validate


def test_every_bundled_tool_signature_matches_its_declared_convention():
    checked = []
    for path in sorted(Path("ultron/actions").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        tool_node = next((node.value for node in tree.body
                          if isinstance(node, ast.Assign)
                          and any(isinstance(t, ast.Name) and t.id == "TOOL" for t in node.targets)), None)
        if tool_node is None:
            continue
        fields = dict(zip((ast.literal_eval(k) for k in tool_node.keys), tool_node.values, strict=True))
        handler_name = fields["handler"].id
        original = next(node for node in tree.body
                        if isinstance(node, ast.FunctionDef) and node.name == handler_name)
        # Retain the real argument shape but remove annotations/default effects
        # and the body. This tests binding only, never runtime behavior.
        args = original.args
        for arg in args.posonlyargs + args.args + args.kwonlyargs:
            arg.annotation = None
        if args.vararg:
            args.vararg.annotation = None
        if args.kwarg:
            args.kwarg.annotation = None
        args.defaults = [ast.Constant(None) for _ in args.defaults]
        args.kw_defaults = [ast.Constant(None) if v is not None else None for v in args.kw_defaults]
        stub = ast.FunctionDef(name=handler_name, args=args, body=[ast.Pass()],
                               decorator_list=[], returns=None, type_comment=None)
        namespace = {}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[stub], type_ignores=[])), str(path), "exec"), namespace)
        tool = {key: ast.literal_eval(fields[key]) for key in
                ("name", "description", "parameters", "argument_mode") if key in fields}
        tool["handler"] = namespace[handler_name]
        record = _validate(SimpleNamespace(TOOL=tool), path.name)
        assert record.valid, f"{path}: {record.error}"
        checked.append(record.name)
    assert len(checked) >= 61  # Guard against accidentally testing an empty directory.
