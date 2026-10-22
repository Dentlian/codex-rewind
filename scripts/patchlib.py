import hashlib
import json
import pathlib
import shutil
import struct
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1] / '.work'
INITIAL = 'webview/assets/app-initial-83973da15da9.js'
MENU = 'webview/assets/sites-end-resource-b8e3f57525e9.js'

def replace_once(source, old, new):
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f'Unsupported application build: expected one match, got {count}: {old[:100]}')
    return source.replace(old, new, 1)

def patch_sources():
    base = ROOT / 'codex-app'
    out = ROOT / 'patched'
    out.mkdir(exist_ok=True)
    initial = (base / INITIAL).read_text(encoding='utf-8')
    controller = (pathlib.Path(__file__).resolve().parents[1] / 'src/rewind-controller.js').read_text(encoding='utf-8')
    initial = replace_once(initial,
        'getConversation(e){return this.threadStore.getConversation(e)}',
        'getConversation(e){globalThis.__codexRewind?.registerManager(e,this);return this.threadStore.getConversation(e)}')
    # ESM module initialization finishes before any conversation manager is created.
    initial += '\n;' + controller + '\n'
    menu = (base / MENU).read_text(encoding='utf-8')
    menu = replace_once(menu,
        'renderUsedSkillsDetails:j,forkDisabled:I,forkLabel:ie,isForking:L,onFork:y,open:te,onOpenChange:ne}',
        'renderUsedSkillsDetails:j,forkDisabled:I,forkLabel:ie,isForking:L,onFork:y,open:te,onOpenChange:ne,rewindThreadId:x,rewindTurnId:o}')
    menu = replace_once(menu,
        '):x=t[10];let S;t[11]===_?',
        '):x=t[10];x=(0,Px.jsxs)(Px.Fragment,{children:[x,e.rewindTurnId==null?null:(0,Px.jsx)(Zn.Item,{leftIcon:(0,Px.jsx)(`span`,{"aria-hidden":!0,children:`↶`}),disabled:o||c||!globalThis.__codexRewind?.canRun(e.rewindThreadId,e.rewindTurnId),onSelect:()=>{globalThis.__codexRewind?.run(e.rewindThreadId,e.rewindTurnId).catch(error=>console.error("Codex rewind",error))},children:`回退到本轮之前`})]});let S;t[11]===_?')
    outputs = {INITIAL: initial.encode(), MENU: menu.encode()}
    for p, data in outputs.items():
        target = out / p
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return outputs

def rebuild_asar(src, dest, replacements):
    with src.open('rb') as f:
        prefix = f.read(16)
        header_size = struct.unpack_from('<I', prefix, 4)[0]
        json_size = struct.unpack_from('<I', prefix, 12)[0]
        header = json.loads(f.read(json_size))
        start = 8 + header_size
        entries = []
        def walk(files, parent=''):
            for name, info in files.items():
                p = parent + name
                if 'files' in info:
                    walk(info['files'], p + '/')
                elif 'offset' in info and not info.get('unpacked'):
                    entries.append((p, info, int(info['offset']), info['size']))
        walk(header['files'])
        entries.sort(key=lambda x:x[2])
        offset = 0
        for p, info, _, size in entries:
            info['offset'] = str(offset)
            data = replacements.get(p)
            if data is not None:
                info['size'] = len(data)
                size = len(data)
                block_size = info.get('integrity', {}).get('blockSize', 4194304)
                info['integrity'] = {'algorithm': 'SHA256', 'hash': hashlib.sha256(data).hexdigest(),
                    'blockSize': block_size, 'blocks': [hashlib.sha256(data[i:i+block_size]).hexdigest() for i in range(0,len(data),block_size)]}
            offset += size
        raw = json.dumps(header, separators=(',', ':'), ensure_ascii=False).encode()
        # Chromium Pickle: length-prefixed, 4-byte-aligned string, wrapped in another Pickle.
        payload = struct.pack('<I', len(raw)) + raw
        payload += b'\0' * ((-len(payload)) % 4)
        header_pickle = struct.pack('<I', len(payload)) + payload
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open('wb') as out:
            out.write(struct.pack('<II', 4, len(header_pickle)))
            out.write(header_pickle)
            for p, info, original_offset, original_size in entries:
                if p in replacements:
                    out.write(replacements[p])
                else:
                    f.seek(start + original_offset)
                    remaining = original_size
                    while remaining:
                        data = f.read(min(remaining, 1048576))
                        if not data: raise RuntimeError('Unexpected archive end')
                        out.write(data)
                        remaining -= len(data)
    return hashlib.sha256(raw).hexdigest()
