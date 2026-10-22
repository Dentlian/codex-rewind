"""Build an independent copy from a locally installed, supported Codex build."""
import argparse
import hashlib
import json
import pathlib
import shutil
import struct
import subprocess

from patchlib import INITIAL, MENU, ROOT, patch_sources, rebuild_asar

PROJECT = pathlib.Path(__file__).resolve().parents[1]
SUPPORTED_HEADER_SHA256 = '261a84fbb5019f9386e50095c75e4cea2ae5cdb53cd9775eba2bb3af1c91fa88'

def read_header(archive):
    with archive.open('rb') as stream:
        prefix = stream.read(16)
        if len(prefix) != 16:
            raise ValueError('Invalid ASAR header')
        header_size = struct.unpack_from('<I', prefix, 4)[0]
        json_size = struct.unpack_from('<I', prefix, 12)[0]
        if not 0 < json_size <= 32 * 1024 * 1024 or header_size < json_size + 8:
            raise ValueError('Invalid ASAR header size')
        raw = stream.read(json_size)
        if hashlib.sha256(raw).hexdigest() != SUPPORTED_HEADER_SHA256:
            raise ValueError('Unsupported or already modified Codex build; refusing to patch')
    return json.loads(raw), 8 + header_size

def extract_resources(archive, header, data_start):
    with archive.open('rb') as stream:
        for filename in (INITIAL, MENU):
            entry = header
            for part in filename.split('/'):
                entry = entry['files'][part]
            if entry.get('unpacked') or 'offset' not in entry:
                raise ValueError('Unsupported resource layout')
            stream.seek(data_start + int(entry['offset']))
            data = stream.read(entry['size'])
            if len(data) != entry['size']:
                raise ValueError('Truncated resource')
            if hashlib.sha256(data).hexdigest() != entry['integrity']['hash']:
                raise ValueError('Original resource integrity mismatch')
            target = ROOT / 'codex-app' / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

def build(source, target, prepare_only=False):
    source = source.resolve(strict=True)
    archive = source / 'resources/app.asar'
    header, data_start = read_header(archive)
    binary = (source / 'ChatGPT.exe').read_bytes()
    if binary.count(SUPPORTED_HEADER_SHA256.encode()) != 1:
        raise ValueError('Unsupported executable resource integrity layout')
    if not prepare_only:
        target = target.resolve()
        if not target.is_relative_to(PROJECT / 'dist') or target == PROJECT / 'dist':
            raise ValueError('Output must be a new subdirectory of this project dist directory')
        if target.exists():
            raise FileExistsError('Output exists; choose a new directory to preserve the existing copy')
    extract_resources(archive, header, data_start)
    replacements = patch_sources()
    node = shutil.which('node')
    if not node:
        raise RuntimeError('Node.js is required for patched JavaScript syntax checks')
    for filename in replacements:
        subprocess.run([node, '--check', str(ROOT / 'patched' / filename)], check=True)
    if prepare_only:
        print('Resources prepared and JavaScript syntax checked. No application copy created.')
        return
    target.mkdir(parents=True)
    app = target / 'app'
    def ignore(directory, names):
        return ['app.asar'] if pathlib.Path(directory) == source / 'resources' else []
    shutil.copytree(source, app, ignore=ignore)
    digest = rebuild_asar(archive, app / 'resources/app.asar', replacements)
    # Preserve integrity enforcement; bind the independent executable to its rebuilt archive.
    # This changes the independent executable's signature. The installed original stays intact.
    (app / 'ChatGPT.exe').write_bytes(binary.replace(SUPPORTED_HEADER_SHA256.encode(), digest.encode(), 1))
    shutil.copy2(PROJECT / 'scripts/launch-rewind.cmd', target / 'launch-rewind.cmd')
    (target / 'build-info.json').write_text(json.dumps({
        'rewindVersion': '0.1.0', 'supportedWindowsPackage': '26.1016.8120.0',
        'asarHeaderSha256': digest, 'changedResources': list(replacements),
        'officialSignedDistribution': False,
    }, indent=2) + '\n', encoding='utf-8')
    print('Independent build completed. Exit original Codex before using the launcher in dist.')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=pathlib.Path, required=True, help='Installed Codex app directory')
    parser.add_argument('--output', type=pathlib.Path, default=PROJECT / 'dist/Codex-Rewind')
    parser.add_argument('--prepare-only', action='store_true', help='Prepare local resources for menu testing without copying the app')
    args = parser.parse_args()
    build(args.source, args.output, args.prepare_only)
