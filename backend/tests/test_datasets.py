from contextlib import contextmanager
from uuid import uuid4
import unittest
from pathlib import Path
from app.datasets import safe_path, lfw_samples, wider_samples

@contextmanager
def test_directory():
    # Python 3.14's Windows mode=0700 temporary dirs conflict with sandbox ACLs.
    base = Path(__file__).resolve().parent / '.fixtures'
    root = base / uuid4().hex
    root.mkdir(parents=True)
    try:
        yield str(root)
    finally:
        assert root.resolve().is_relative_to(base.resolve())
        for path in sorted(root.rglob('*'), key=lambda p: len(p.parts), reverse=True):
            path.rmdir() if path.is_dir() else path.unlink()
        root.rmdir()

class DatasetTests(unittest.TestCase):
    def test_reject_traversal(self):
        with test_directory() as tmp:
            with self.assertRaises(ValueError):
                safe_path(Path(tmp), '../outside.jpg')

    def test_lfw(self):
        with test_directory() as tmp:
            root = Path(tmp)
            person = root / 'lfw' / 'Test_Person'
            person.mkdir(parents=True)
            (person / 'Test_Person_0001.jpg').touch()
            row, = lfw_samples(root, 'lfw')
            self.assertEqual(row['label'], 'Test_Person')
            self.assertEqual(row['path'], 'lfw/Test_Person/Test_Person_0001.jpg')

    def test_wider_invalid_and_zero_placeholder(self):
        with test_directory() as tmp:
            root = Path(tmp)
            (root / 'images' / 'event').mkdir(parents=True)
            for name in ['one', 'zero', 'last']:
                (root / 'images' / 'event' / f'{name}.jpg').touch()
            (root / 'gt.txt').write_text('event/one.jpg\n2\n1 2 10 20 0 0 0 0 0 0\n0 0 4 5 0 0 0 1 0 0\nevent/zero.jpg\n0\n0 0 0 0 0 0 0 0 0 0\nevent/last.jpg\n1\n2 3 5 6 0 0 0 0 0 0\n')
            rows = list(wider_samples(root, 'images', 'gt.txt', 'val'))
            self.assertEqual([r['boxes'] for r in rows], [[[1, 2, 11, 22]], [], [[2, 3, 7, 9]]])

    def test_missing_image(self):
        with test_directory() as tmp:
            root = Path(tmp)
            (root / 'images').mkdir()
            (root / 'gt.txt').write_text('missing.jpg\n1\n0 0 4 5 0 0 0 0 0 0\n')
            with self.assertRaises(ValueError):
                list(wider_samples(root, 'images', 'gt.txt', 'train'))
