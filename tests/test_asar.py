import hashlib
import json
import pathlib
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
from patchlib import rebuild_asar, replace_once
from build import read_header

def archive(path, entries):
    files = {}
    offset = 0
    body = b''
    for name, content in entries.items():
        files[name] = {'size': len(content), 'offset': str(offset)}
        body += content
        offset += len(content)
    files['external.bin'] = {'size': 3, 'unpacked': True}
    raw = json.dumps({'files': files}, separators=(',', ':')).encode()
    payload = struct.pack('<I', len(raw)) + raw
    payload += b'\0' * (-len(payload) % 4)
    header = struct.pack('<I', len(payload)) + payload
    path.write_bytes(struct.pack('<II', 4, len(header)) + header + body)

def unpack(path):
    data = path.read_bytes()
    size = struct.unpack_from('<I', data, 4)[0]
    raw = data[16:16 + struct.unpack_from('<I', data, 12)[0]]
    header = json.loads(raw)
    content = {}
    for name, info in header['files'].items():
        if 'offset' in info:
            start = 8 + size + int(info['offset'])
            content[name] = data[start:start + info['size']]
    return raw, header, content

class ArchiveTests(unittest.TestCase):
    def test_rebuild_preserves_unmodified_data_and_updates_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            source = pathlib.Path(directory) / 'original.asar'
            output = pathlib.Path(directory) / 'changed.asar'
            archive(source, {'first.js': b'old', 'empty.txt': b'', 'other.txt': b'preserve me'})
            original = source.read_bytes()
            replacement = b'new content with different size'
            digest = rebuild_asar(source, output, {'first.js': replacement})
            raw, header, contents = unpack(output)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(contents, {'first.js': replacement, 'empty.txt': b'', 'other.txt': b'preserve me'})
            self.assertEqual(digest, hashlib.sha256(raw).hexdigest())
            self.assertEqual(header['files']['first.js']['integrity']['hash'], hashlib.sha256(replacement).hexdigest())
            self.assertEqual(header['files']['external.bin'], {'size': 3, 'unpacked': True})

    def test_unsupported_archive_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = pathlib.Path(directory) / 'synthetic.asar'
            archive(source, {'test.js': b'synthetic'})
            with self.assertRaisesRegex(ValueError, 'Unsupported'):
                read_header(source)

    def test_ambiguous_or_absent_patch_anchor_is_rejected(self):
        for source in ['nothing', 'anchor anchor']:
            with self.assertRaises(RuntimeError):
                replace_once(source, 'anchor', 'replacement')
        self.assertEqual(replace_once('an anchor here', 'anchor', 'item'), 'an item here')

if __name__ == '__main__':
    unittest.main()
