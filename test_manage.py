import tempfile
import unittest
from pathlib import Path
from manage import transfer


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.skill = self.source / 'example'
        self.skill.mkdir(parents=True)
        (self.skill / 'SKILL.md').write_text('---\nname: example\ndescription: Example\n---\n')
        self.dest = self.root / 'destination'

    def tearDown(self):
        self.temp.cleanup()

    def test_round_trip_preserves_content_and_excludes_caches(self):
        (self.skill / '__pycache__').mkdir()
        (self.skill / '__pycache__/generated.pyc').write_bytes(b'cache')
        installed, skipped, _ = transfer(self.source, self.dest)
        self.assertEqual(installed, ['example'])
        self.assertEqual(skipped, [])
        self.assertFalse((self.dest / 'example/__pycache__').exists())
        restored = self.root / 'restored'
        transfer(self.dest, restored)
        self.assertEqual((restored / 'example/SKILL.md').read_bytes(), (self.skill / 'SKILL.md').read_bytes())

    def test_skip_and_replace_preserve_local_changes(self):
        transfer(self.source, self.dest)
        target = self.dest / 'example/SKILL.md'
        target.write_text('local changes')
        self.assertEqual(transfer(self.source, self.dest)[1], ['example'])
        self.assertEqual(target.read_text(), 'local changes')
        _, _, backup = transfer(self.source, self.dest, replace=True)
        self.assertEqual((backup / 'example/SKILL.md').read_text(), 'local changes')
        self.assertEqual(target.read_bytes(), (self.skill / 'SKILL.md').read_bytes())

    def test_system_skills_and_credentials_are_not_exported(self):
        hidden = self.source / '.system/internal'
        hidden.mkdir(parents=True)
        (hidden / 'SKILL.md').write_text('internal')
        (self.skill / '.env').write_text('SECRET=not-for-export')
        transfer(self.source, self.dest)
        self.assertFalse((self.dest / '.system').exists())
        self.assertFalse((self.dest / 'example/.env').exists())

    def test_secret_blocks_copy_without_displaying_value(self):
        secret = 'tm_test_' + 'x' * 30
        (self.skill / 'bad.txt').write_text(secret)
        with self.assertRaises(ValueError) as error:
            transfer(self.source, self.dest)
        self.assertNotIn(secret, str(error.exception))
        self.assertFalse(self.dest.exists())

    def test_overlap_rejected(self):
        with self.assertRaises(ValueError):
            transfer(self.source, self.source / 'nested')


if __name__ == '__main__':
    unittest.main()
