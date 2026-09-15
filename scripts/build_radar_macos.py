"""Build a local Apple Silicon app from pinned archives and offline wheels.

No downloads, publication, notarization or user installation. Build with this
checkout's development Python; the resulting app carries its own interpreter.
Ad-hoc signing permits local testing and does not identify a trusted publisher.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import plistlib
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

from install_radar import PROJECTS, environment, pip, wheel_lock

ROOT = Path(__file__).resolve().parents[1]
PYTHON_SHA = '768f05cf200273bbdda9a5955a5a6892a4b22f2a0b1e4b0a9160f5c7fce86816'
GIT_SHA = '457fdb04dc8728e007d4688695e6912e6f680727920f2a40bf11eacc17505357'
GIT_OPTIONS = ['NO_CURL=YesPlease', 'NO_OPENSSL=YesPlease', 'NO_GETTEXT=YesPlease',
    'NO_EXPAT=YesPlease', 'NO_TCLTK=YesPlease', 'NO_PERL=YesPlease',
    'NO_PYTHON=YesPlease', 'NO_RUST=YesPlease', 'CFLAGS=-O2 -mmacosx-version-min=12.0']


def sha(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def extract(archive, expected, target):
    if archive.is_symlink() or sha(archive) != expected:
        raise ValueError('Pinned source archive checksum mismatch')
    target.mkdir()
    with tarfile.open(archive) as source:
        source.extractall(target, filter='data')


def run(args, cwd):
    subprocess.run([str(arg) for arg in args], cwd=cwd, env=environment(), check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['runtime-archive', 'git-archive', 'project-wheels', 'wheelhouse', 'output', 'work-dir']:
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != 'darwin' or platform.machine() != 'arm64':
        parser.error('This local candidate is Apple Silicon only')
    args.output = args.output.absolute()
    args.work_dir = args.work_dir.absolute()
    if args.output.exists() or args.work_dir.exists():
        parser.error('Use new output and work paths; existing files are never replaced')
    args.work_dir.mkdir(parents=True)
    extract(args.runtime_archive, PYTHON_SHA, args.work_dir / 'python')
    extract(args.git_archive, GIT_SHA, args.work_dir / 'git')
    git_source = args.work_dir / 'git/git-2.55.0'
    run(['/usr/bin/make', '-j4', 'git', *GIT_OPTIONS], git_source)

    contents = args.output / 'Contents'
    resources = contents / 'Resources'
    (contents / 'MacOS').mkdir(parents=True)
    resources.mkdir()
    runtime = resources / 'runtime'
    shutil.copytree(args.work_dir / 'python/python', runtime, symlinks=True)
    python = runtime / 'bin/python3.11'
    wheels = args.work_dir / 'wheels'
    wheels.mkdir()
    pip(python, 'download', ['--no-deps', '-r', ROOT / 'requirements/radar-runtime.lock', '--dest', wheels],
        cwd=args.work_dir, wheelhouse=args.wheelhouse.absolute(), offline=True)
    for name in PROJECTS:
        shutil.copyfile(args.project_wheels / name, wheels / name)
    lock = args.work_dir / 'wheels.lock'
    wheel_lock(wheels, lock)
    pip(python, 'install', ['--no-compile', '-r', lock], cwd=args.work_dir, wheelhouse=wheels, offline=True)
    # pip console launchers are unnecessary and encode the build path. The app
    # invokes Python with -I -B -m; retain only the runtime's relative executables.
    for p in (runtime / 'bin').iterdir():
        if p.is_file() and not p.is_symlink() and p.read_bytes()[:2] == b'#!':
            p.unlink()
    for p in (runtime / 'bin').iterdir():
        if p.is_symlink() and not p.exists():
            p.unlink()
    for p in runtime.rglob('*.pyc'):
        p.unlink()
    # Precompile before signing. Checked source hashes survive relocation and
    # avoid compiling every library on each short-lived hook. Runtime -B still
    # prevents writes to the signed app. Strip the private builder path.
    run([python, '-I', '-B', '-m', 'compileall', '-q', '-f',
        '--invalidation-mode', 'checked-hash', '-s', runtime, '-p', '/forkit-runtime',
        runtime / 'lib/python3.11'], args.work_dir)
    git_bin = resources / 'git/bin/git'
    git_bin.parent.mkdir(parents=True)
    shutil.copyfile(git_source / 'git', git_bin)
    git_bin.chmod(0o755)
    licenses = resources / 'Licenses'
    licenses.mkdir()
    shutil.copyfile(ROOT / 'packages/radar/LICENSE', licenses / 'Forkit-APACHE-2.0.txt')
    shutil.copyfile(git_source / 'COPYING', licenses / 'Git-COPYING.txt')
    # Ship corresponding Git source and exact build options beside its binary.
    shutil.copyfile(args.git_archive, licenses / 'git-2.55.0.tar.xz')
    (licenses / 'Git-build.json').write_text(json.dumps({'sha256': GIT_SHA, 'make': ['git', *GIT_OPTIONS]}, indent=2) + '\n')
    (resources / 'BUILD.json').write_text(json.dumps({'format': 1, 'channel': 'local-beta-candidate',
        'python': {'version': '3.11.16', 'release': '20260901', 'archive_sha256': PYTHON_SHA},
        'git': {'version': '2.55.0', 'archive_sha256': GIT_SHA},
        'wheels': {p.name: sha(p) for p in wheels.iterdir()}, 'publisher_verified': False,
        'notarized': False, 'bytecode': 'checked-hash-python3.11'}, indent=2, sort_keys=True) + '\n')
    sdk = subprocess.check_output(['/usr/bin/xcrun', '--show-sdk-path'], text=True).strip()
    run(['/usr/bin/xcrun', 'swiftc', '-sdk', sdk, '-O', '-target', 'arm64-apple-macosx12.0',
        '-framework', 'AppKit', '-framework', 'WebKit', ROOT / 'packages/radar/macos/Forkit.swift',
        '-o', contents / 'MacOS/Forkit'], args.work_dir)
    run(['/usr/bin/xcrun', 'swiftc', '-sdk', sdk, '-O', '-target', 'arm64-apple-macosx12.0',
        ROOT / 'packages/radar/macos/FileActions.swift', '-o', contents / 'MacOS/ForkitFileActions'], args.work_dir)
    info = {'CFBundleIdentifier': 'dev.forkit.session-receipt', 'CFBundleName': 'Forkit Session Receipt',
        'CFBundleDisplayName': 'Forkit Session Receipt', 'CFBundleExecutable': 'Forkit',
        'CFBundlePackageType': 'APPL', 'CFBundleShortVersionString': '0.1.0', 'CFBundleVersion': '5.0',
        'LSMinimumSystemVersion': '12.0', 'LSArchitecturePriority': ['arm64'],
        'NSHighResolutionCapable': True, 'NSPrincipalClass': 'NSApplication',
        'NSHumanReadableCopyright': 'Forkit contributors · Apache-2.0'}
    (contents / 'Info.plist').write_bytes(plistlib.dumps(info))
    # Sign Mach-O files individually before the outer bundle. These local
    # signatures are not Developer ID and must never be marketed as notarized.
    macho = {b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca'}
    for p in sorted(contents.rglob('*')):
        if p.is_file() and not p.is_symlink():
            with p.open('rb') as source:
                native = source.read(4) in macho
            if native:
                run(['/usr/bin/codesign', '--force', '--sign', '-', p], args.work_dir)
    (runtime / 'forkit-runtime.json').write_text(json.dumps({'format': 1, 'git_sha256': sha(git_bin)}) + '\n')
    (resources / 'forkit-file-actions.json').write_text(json.dumps({'format': 1,
        'sha256': sha(contents / 'MacOS/ForkitFileActions')}) + '\n')
    run(['/usr/bin/codesign', '--force', '--sign', '-', args.output], args.work_dir)
    run(['/usr/bin/codesign', '--verify', '--strict', args.output], args.work_dir)
    files = {}
    for p in sorted(args.output.rglob('*')):
        relative = str(p.relative_to(args.output))
        if p.is_symlink():
            if not p.resolve().is_relative_to(args.output):
                raise ValueError('Bundle contains an external symlink')
            files[relative] = {'link': os.readlink(p)}
        elif p.is_file():
            files[relative] = {'sha256': sha(p), 'mode': p.stat().st_mode & 0o777}
    manifest = args.work_dir / 'app-manifest.json'
    manifest.write_text(json.dumps({'format': 1, 'files': files}, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'app': str(args.output), 'manifest': str(manifest), 'manifest_sha256': sha(manifest),
        'installed': False, 'notarized': False}))


if __name__ == '__main__':
    main()
