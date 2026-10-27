#!/usr/bin/env python3
"""Xboard-only release worker. No credentials or customer data in output.

The installed copy is root-owned and is never updated by polling repository code.
"""
import argparse
from contextlib import closing
import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request

APP = Path('/opt/1panel/apps/xboard')
COMPOSE = APP / 'compose.yaml'
MIRROR = Path('/var/cache/github-deploy/repos/xboard.git')
STATE = Path('/var/lib/xboard-release')
STAGING_ROOT = Path('/var/cache/github-deploy/staging')
REPOSITORY = 'https://github.com/GaoSeafood/Xboard.git'
CONTAINER = 'xboard-xboard-1'
LOCAL_URL = 'http://127.0.0.1:7001'
PUBLIC_URL_FILE = Path('/etc/github-deploy/xboard-public-url')
SHA = re.compile(r'^[a-f0-9]{40}$')
THEME_TARGETS = {
    '/www/theme/Xboard/dashboard.blade.php', '/www/theme/Xboard/config.json',
    '/www/theme/Xboard/env.example.js', '/www/theme/Xboard/index.html',
    '/www/theme/Xboard/assets/brand',
}


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def run(args, timeout=120):
    # Never forward arbitrary build/runtime output, which may include private data.
    result = subprocess.run([str(x) for x in args], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=timeout)
    if result.returncode:
        raise RuntimeError('%s failed (exit %s)' % (args[0], result.returncode))
    return result.stdout.decode().strip()


def git(*args):
    return run(['git', '-C', MIRROR, *args])


def ancestor(first, second):
    result = subprocess.run(['git', '-C', str(MIRROR), 'merge-base', '--is-ancestor',
                             first, second], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if result.returncode not in (0, 1):
        raise RuntimeError('Cannot establish source ancestry')
    return result.returncode == 0


def atomic_write(path, data, mode=0o600):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', dir=str(path.parent))
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, 'w') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def save_state(sha, status, **details):
    atomic_write(STATE / 'status.json', json.dumps(dict(sha=sha, status=status,
                 updatedAt=now(), **details)) + '\n')


def inspect():
    return json.loads(run(['docker', 'inspect', CONTAINER]))[0]


def revision(container):
    return container['Config'].get('Labels', {}).get('org.opencontainers.image.revision', '')


def fetch_master():
    if not MIRROR.is_dir():
        raise RuntimeError('Provision the source mirror before enabling deployment')
    if git('remote', 'get-url', 'origin') != REPOSITORY:
        raise RuntimeError('Source mirror does not point to the owned fork')
    git('fetch', '--quiet', 'origin', '+refs/heads/master:refs/heads/master')
    return git('rev-parse', 'refs/heads/master')


def validate_target(target, head, current):
    if not SHA.fullmatch(target) or not SHA.fullmatch(current):
        raise RuntimeError('Missing or invalid source revision')
    if not ancestor(target, head):
        raise RuntimeError('Requested commit is not on master')
    if not ancestor(current, target):
        raise RuntimeError('Refusing an outdated event or a non-fast-forward release')


def validate_changes(paths):
    # Compare with the running release, not with the event's before SHA.
    if any(re.search(r'(^|/)(database|migrations?|schema)(/|$)|(^|/)\.env($|\.)', p)
           for p in paths):
        raise RuntimeError('Database or environment changes require a reviewed manual release')


def release_compose(text, image):
    """Preserve existing configuration; remove only legacy source-code mounts."""
    lines = text.splitlines(keepends=True)
    output = []
    service = False
    found_image = False
    for line in lines:
        if re.match(r'^  xboard:\s*$', line):
            service = True
        elif service and re.match(r'^  [^ #\s][^:]*:', line):
            service = False
        if service and re.match(r'^    image:', line):
            output.append('    image: ' + image + '\n')
            found_image = True
            continue
        if service:
            match = re.match(r'^\s+-\s+[\x27\x22]?([^:]+):([^:\s\x27\x22]+)(?::[^\s]+)?[\x27\x22]?\s*$', line)
            if match and match.group(2) in THEME_TARGETS:
                if not match.group(1).startswith('./releases/'):
                    raise RuntimeError('Unexpected theme override; review before removing it')
                continue
        output.append(line)
    if not found_image:
        raise RuntimeError('Unexpected Compose layout; no xboard image updated')
    return ''.join(output)


def get(url):
    request = urllib.request.Request(url, headers={'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(request, timeout=12) as response:
        if response.status != 200:
            raise RuntimeError('Health request did not return 200')
        return response.read(5 * 1024 * 1024)


def public_url():
    value = PUBLIC_URL_FILE.read_text().strip().rstrip('/')
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.query:
        raise RuntimeError('Configure a public HTTPS health URL')
    return value


def verify_http(base, target):
    marker = json.loads(get(base + '/release.json?revision=' + target))
    if marker.get('revision') != target:
        raise RuntimeError('HTTP release revision does not match requested source')
    page = get(base + '/?release_check=' + target).decode()
    if '筋斗云' not in page or '/assets/ez-theme/' not in page:
        raise RuntimeError('Expected branded theme was not rendered')
    assets = set(re.findall(r'(?:src|href)=[\x27\x22](/theme/[^\x27\x22]+)', page))
    if not any('.js' in asset for asset in assets):
        raise RuntimeError('Theme JavaScript entry is missing')
    for asset in assets:
        get(base + asset)


def healthy(target, image, endpoint):
    container = inspect()
    if container['State']['Status'] != 'running' or container['Image'] != image or revision(container) != target:
        raise RuntimeError('Container image or source revision mismatch')
    states = run(['docker', 'exec', CONTAINER, 'supervisorctl', '-c',
                  '/etc/supervisor/conf.d/supervisord.conf', 'status'])
    for program in ['octane', 'horizon', 'redis', 'caddy']:
        if not re.search(r'^' + program + r'(?::' + program + r')?(?:_\d+)?\s+RUNNING\b', states, re.M):
            raise RuntimeError(program + ' is not running')
    if any(m['Destination'] in THEME_TARGETS for m in container['Mounts']):
        raise RuntimeError('Legacy theme overrides still cover image files')
    verify_http(LOCAL_URL, target)
    verify_http(endpoint, target)


def backup(previous, current):
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    directory = APP / 'backups' / ('release-' + stamp + '-' + current[:12])
    directory.mkdir(mode=0o700, parents=True)
    os.chmod(directory, 0o700)
    for source in [COMPOSE, APP / '.env']:
        # Copy without reading credentials into the assistant or command output.
        shutil.copyfile(source, directory / source.name)
        os.chmod(directory / source.name, 0o600)
    source = APP / '.docker/.data/database.sqlite'
    if not source.is_file():
        raise RuntimeError('Expected SQLite database missing; no release attempted')
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=30)) as live:
        with closing(sqlite3.connect(str(directory / 'database.sqlite'))) as copy:
            live.backup(copy, pages=1024, sleep=0.1)
            if copy.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise RuntimeError('Database backup integrity check failed')
            copy.execute('PRAGMA journal_mode=DELETE')
    os.chmod(directory / 'database.sqlite', 0o600)
    atomic_write(directory / 'release.json', json.dumps(dict(previousImage=previous,
                 previousRevision=current, createdAt=now())) + '\n')
    return directory


def compose_up():
    run(['docker', 'compose', '--project-directory', APP, '--project-name', 'xboard',
         '--file', COMPOSE, 'up', '-d', '--no-deps', '--no-build', '--force-recreate',
         'xboard'], timeout=180)


def deploy(args):
    head = fetch_master()
    target = head if args.poll else args.sha.lower()
    container = inspect()
    current = revision(container)
    validate_target(target, head, current)
    if current == target:
        healthy(target, container['Image'], public_url())
        print('Xboard already runs ' + target)
        return
    if args.poll and not args.retry and (STATE / 'status.json').is_file():
        old = json.loads((STATE / 'status.json').read_text())
        if old.get('sha') == target and old.get('status') == 'failed':
            print('Previous attempt failed for this revision; manual --retry required')
            return
    save_state(target, 'building', previousRevision=current)
    changed = git('diff', '--name-only', current, target).splitlines()
    validate_changes(changed)
    endpoint = public_url()
    if container['State']['Status'] != 'running':
        raise RuntimeError('Current container is not running')
    get(LOCAL_URL + '/')
    get(endpoint + '/')
    previous = container['Image']
    image_ref = 'localhost/github-deploy/xboard:' + target
    staging_root = STAGING_ROOT
    staging_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='xboard.', dir=str(staging_root)) as stage:
        archive = subprocess.run(['git', '-C', str(MIRROR), 'archive', target],
                                 capture_output=True, check=True).stdout
        subprocess.run(['tar', '-xf', '-', '-C', stage], input=archive, check=True)
        run(['docker', 'build', '--pull', '--build-arg', 'REPO_URL=' + REPOSITORY,
             '--build-arg', 'SOURCE_SHA=' + target, '--label',
             'org.opencontainers.image.revision=' + target, '--tag', image_ref, stage], timeout=3600)
    built = json.loads(run(['docker', 'image', 'inspect', image_ref]))[0]
    if built['Config'].get('Labels', {}).get('org.opencontainers.image.revision') != target:
        raise RuntimeError('Built image revision mismatch')
    old_compose = COMPOSE.read_text()
    candidate = release_compose(old_compose, image_ref)
    # Validate without emitting the resolved environment or production configuration.
    fd, candidate_path = tempfile.mkstemp(prefix='.release-', suffix='.yaml', dir=str(APP))
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(candidate)
        run(['docker', 'compose', '--project-directory', APP, '--file', candidate_path,
             'config', '--quiet'])
    finally:
        os.unlink(candidate_path)
    checkpoint = backup(previous, current)
    run(['docker', 'image', 'tag', previous, 'localhost/github-deploy/xboard:rollback'])
    # Preserve a unique image tag for every checkpoint, even after later releases.
    run(['docker', 'image', 'tag', previous, 'localhost/github-deploy/xboard:' + checkpoint.name])
    save_state(target, 'deploying', previousRevision=current, backup=str(checkpoint))
    atomic_write(COMPOSE, candidate)
    try:
        compose_up()
        for attempt in range(60):
            try:
                healthy(target, built['Id'], endpoint)
                break
            except Exception:
                if attempt == 59:
                    raise RuntimeError('Release health verification did not pass')
                time.sleep(3)
        # A second sample catches workers that enter a restart loop after startup.
        time.sleep(15)
        healthy(target, built['Id'], endpoint)
        run(['docker', 'image', 'tag', image_ref, 'localhost/github-deploy/xboard:current'])
    except Exception:
        # Use the immutable previous image ID, not a mutable current alias.
        restored = re.sub(r'(?m)^    image:.*$', '    image: ' + previous, old_compose)
        atomic_write(COMPOSE, restored)
        compose_up()
        for attempt in range(30):
            try:
                if inspect()['Image'] != previous:
                    raise RuntimeError('Rollback image mismatch')
                get(LOCAL_URL + '/')
                get(endpoint + '/')
                break
            except Exception:
                if attempt == 29:
                    raise RuntimeError('Release and rollback health checks failed')
                time.sleep(3)
        raise RuntimeError('Release failed health checks; previous image and Compose restored')
    save_state(target, 'succeeded', image=built['Id'], backup=str(checkpoint), publicUrl=endpoint)
    print('Xboard deployed and verified ' + target + ' image=' + built['Id'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('sha', nargs='?', default='')
    parser.add_argument('before', nargs='?', default='', help='Legacy webhook argument; not trusted for scope')
    parser.add_argument('--poll', action='store_true')
    parser.add_argument('--retry', action='store_true')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Must run as root')
    if not args.poll and not SHA.fullmatch(args.sha.lower()):
        parser.error('Provide a full commit SHA or --poll')
    os.umask(0o077)
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    with open(STATE / 'release.lock', 'w') as lock:
        # Wait for the other entry point; never report a queued webhook as deployed.
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            deploy(args)
        except Exception as error:
            # Errors intentionally exclude subprocess output and private configuration.
            previous = json.loads((STATE / 'status.json').read_text()) if (STATE / 'status.json').exists() else {}
            target = args.sha or previous.get('sha', '')
            save_state(target, 'failed', message=str(error))
            print('Xboard deployment failed: ' + str(error), flush=True)
            return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
