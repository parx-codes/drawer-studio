"""Prepara archivi sorgenti e portabile, escludendo ambiente e file temporanei."""
from pathlib import Path
import hashlib
import platform
import shutil
import zipfile
import sys


def main():
    root=Path(__file__).resolve().parent.parent
    sys.path.insert(0,str(root))
    from drawer import __version__, APP_NAME
    release=root/'release'
    release.mkdir(exist_ok=True)
    exclusions={'.venv','build','dist','release','verification-binary','__pycache__','.pytest_cache','.git'}
    source=release/f'DrawER-Studio-v{__version__}-sorgenti.zip'
    created=[source]
    with zipfile.ZipFile(source,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob('*')):
            relative=path.relative_to(root)
            if path.is_file() and not set(relative.parts)&exclusions and not any(part.endswith('.egg-info') for part in relative.parts) and path.suffix not in ('.pyc','.spec'):
                archive.write(path,Path('DrawER-Studio')/relative)
    bundle=root/'dist'/APP_NAME
    if bundle.is_dir():
        for name in ('LICENSE','README.md','ARCHITETTURA.md','ANALISI_ORIGINALE.md','THIRD_PARTY_NOTICES.md','VERIFICA.md','CHANGELOG.md','ROADMAP_v1.1.md'):
            path=root/name
            if path.exists():shutil.copy2(path,bundle/name)
        target=release/f'DrawER-Studio-v{__version__}-{platform.system()}-{platform.machine()}.zip'
        with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(bundle.rglob('*')):
                if path.is_file():archive.write(path,Path(APP_NAME)/path.relative_to(bundle))
        created.append(target)
        print(target.resolve())
    checksum_file=release/f'SHA256SUMS-v{__version__}.txt'
    checksum_file.write_text(''.join(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.name+'\n' for path in created),encoding='utf-8')
    print(source.resolve())


if __name__=='__main__':
    main()
