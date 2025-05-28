import ast
import os


def test_manifest_version():
    base_dir = os.path.dirname(os.path.dirname(__file__))
    manifest_path = os.path.join(base_dir, 'requisition', 'customs', 'addons',
                                 'manufacturing_material_requisitions', '__manifest__.py')
    with open(manifest_path, 'r') as f:
        manifest = ast.literal_eval(f.read())
    assert manifest['version'].startswith('18.0')
