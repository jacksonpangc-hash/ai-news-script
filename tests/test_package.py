import importlib.util
from pathlib import Path
import sys
import tempfile
import shutil
import unittest
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
try:
    import package_skill as pkg
except ImportError:
    pkg=None


class PackageTests(unittest.TestCase):
    def test_embedded_license_and_canonical_bytes_are_required(self):
        for target in ('LICENSE','references/style-pass.md'):
            with self.subTest(target=target),tempfile.TemporaryDirectory() as temp:
                skill=Path(temp)/'ai-news-script'
                shutil.copytree(ROOT/'ai-news-script',skill,ignore=shutil.ignore_patterns('__pycache__'))
                f=skill/'vendor/sepia'/target
                f.write_text('tampered',encoding='utf-8')
                with self.assertRaisesRegex(ValueError,'Vendor'):
                    pkg.build(skill,Path(temp)/'skill.zip')

    def test_vendor_manifest_does_not_admit_unlisted_extra_file(self):
        with tempfile.TemporaryDirectory() as temp:
            skill=Path(temp)/'ai-news-script'
            shutil.copytree(ROOT/'ai-news-script',skill,ignore=shutil.ignore_patterns('__pycache__'))
            (skill/'vendor/sepia/private.txt').write_text('must not distribute',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Unexpected'):
                pkg.build(skill,Path(temp)/'skill.zip')

    def test_release_cannot_omit_license_or_install_guide(self):
        for name in ('LICENSE','INSTALL.md'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                skill=Path(temp)/'ai-news-script'
                shutil.copytree(ROOT/'ai-news-script',skill,ignore=shutil.ignore_patterns('__pycache__'))
                (skill/name).unlink()
                with self.assertRaises(ValueError):
                    pkg.build(skill,Path(temp)/'skill.zip')

    def test_standalone_docs_and_license_survive_install_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            skill=Path(temp)/'ai-news-script'
            shutil.copytree(ROOT/'ai-news-script',skill,ignore=shutil.ignore_patterns('__pycache__'))
            for name in ('README.md','INSTALL.md','USAGE.md','CHANGELOG.md','NOTICE.md','LICENSE'):
                (skill/name).write_text('Public project documentation\n',encoding='utf-8')
            archive=pkg.build(skill,Path(temp)/'skill.zip')
            with ZipFile(archive) as z:
                self.assertEqual(z.read('ai-news-script/LICENSE'),b'Public project documentation\n')
                self.assertIn('ai-news-script/INSTALL.md',z.namelist())

    def test_personal_machine_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            skill=Path(temp)/'ai-news-script'
            shutil.copytree(ROOT/'ai-news-script',skill,ignore=shutil.ignore_patterns('__pycache__'))
            (skill/'references/private.md').write_text('/Users/private-owner/internal-project',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'personal'):
                pkg.build(skill,Path(temp)/'skill.zip')

    def test_distribution_excludes_runtime_and_reopens_as_one_skill(self):
        self.assertIsNotNone(pkg,'packager not implemented')
        with tempfile.TemporaryDirectory() as temp:
            archive=pkg.build(ROOT/'ai-news-script',Path(temp)/'skill.zip')
            with ZipFile(archive) as z:
                names=z.namelist()
                self.assertIn('ai-news-script/SKILL.md',names)
                self.assertTrue(all(n.startswith('ai-news-script/') for n in names))
                self.assertFalse(any('/runtime/' in n or '__pycache__' in n or 'preferences.json' in n for n in names))
                z.extractall(Path(temp)/'reopened')
            self.assertTrue((Path(temp)/'reopened/ai-news-script/scripts/manage_state.py').is_file())


if __name__=='__main__':unittest.main()
