"""Native Windows shared-runtime link tests; no npm download or browser needed."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.name == 'nt', 'Windows junctions only')
class WindowsRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='talkcraft-windows-runtime-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runtime = self.root / 'runtime'
        self.runtime.mkdir()
        self.project = self.root / 'project'
        self.project.mkdir()
        self.script = self.runtime / 'windows-runtime.mjs'
        shutil.copy2(Path(__file__).with_name('windows-runtime.mjs'), self.script)
        self.write(self.runtime / 'package.json', {'dependencies': {'remotion': '4.0.519'}})
        self.write(self.runtime / 'node_modules/remotion/package.json', {'version': '4.0.519'})

    @staticmethod
    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf-8')

    def run_link(self):
        return subprocess.run(['node', str(self.script), 'link', str(self.project)],
                              capture_output=True, text=True, timeout=20)

    def test_link_preserves_project_scripts_and_is_repeatable(self):
        self.write(self.project / 'package.json', {
            'name': 'existing', 'scripts': {'render': 'kept'},
            'dependencies': {'remotion': '4.0.518'},
        })
        for _ in range(2):
            result = self.run_link()
            self.assertEqual(result.returncode, 0, result.stderr)
            modules = self.project / 'node_modules'
            self.assertTrue(modules.is_dir())
            self.assertEqual(modules.resolve(), (self.runtime / 'node_modules').resolve())
            manifest = json.loads((self.project / 'package.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['dependencies']['remotion'], '4.0.519')
            self.assertEqual(manifest['scripts']['render'], 'kept')

    def test_missing_dependency_does_not_change_existing_install(self):
        original = {'dependencies': {'remotion': '4.0.519', 'project-only': '1.0.0'}}
        self.write(self.project / 'package.json', original)
        self.write(self.project / 'node_modules/keep.json', {'keep': True})
        result = self.run_link()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('project-only', result.stderr)
        self.assertEqual(json.loads((self.project / 'package.json').read_text()), original)
        self.assertTrue((self.project / 'node_modules/keep.json').exists())

    def test_existing_dependency_directory_is_not_deleted(self):
        self.write(self.project / 'package.json', {'dependencies': {'remotion': '4.0.519'}})
        self.write(self.project / 'node_modules/keep.json', {'keep': True})
        result = self.run_link()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('already points elsewhere', result.stderr)
        self.assertTrue((self.project / 'node_modules/keep.json').exists())


if __name__ == '__main__':
    unittest.main()
