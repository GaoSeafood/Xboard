import importlib.util
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('release', Path(__file__).parents[1] / 'xboard-release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class SourceSafety(unittest.TestCase):
    def test_rejects_stale_event_and_accepts_exact_ancestor(self):
        with tempfile.TemporaryDirectory() as directory:
            def git(*args):
                return subprocess.check_output(['git', '-C', directory, *args], stderr=subprocess.DEVNULL).decode().strip()
            git('init')
            git('config', 'user.name', 'Test')
            git('config', 'user.email', 'test@example.invalid')
            commits = []
            for number in range(3):
                (Path(directory) / 'source').write_text(str(number))
                git('add', '.')
                git('commit', '-m', str(number))
                commits.append(git('rev-parse', 'HEAD'))
            with patch.object(release, 'MIRROR', Path(directory)):
                release.validate_target(commits[1], commits[2], commits[0])
                with self.assertRaisesRegex(RuntimeError, 'outdated'):
                    release.validate_target(commits[0], commits[2], commits[1])
                with self.assertRaises(RuntimeError):
                    release.validate_target('not-a-sha', commits[2], commits[0])

    def test_blocks_cumulative_migrations_even_if_latest_change_is_docs(self):
        release.validate_changes(['docs/release.md', 'composer.lock'])
        for name in ['database/migrations/change.php', '.env', 'subdir/schema/new.sql']:
            with self.assertRaisesRegex(RuntimeError, 'manual release'):
                release.validate_changes(['docs/release.md', name])


class ConfigurationSafety(unittest.TestCase):
    def test_replaces_only_xboard_image_and_legacy_theme_mounts(self):
        compose = '''name: xboard
services:
  xboard:
    image: old
    volumes:
      - ./.env:/www/.env
      - ./storage/theme:/www/storage/theme
      - ./releases/old/index.html:/www/theme/Xboard/index.html:ro
      - ./releases/old/assets/brand:/www/theme/Xboard/assets/brand:ro
      - ./plugins:/www/plugins
  another:
    image: unchanged
'''
        result = release.release_compose(compose, 'new')
        self.assertIn('    image: new\n', result)
        self.assertIn('    image: unchanged\n', result)
        self.assertIn('./.env:/www/.env', result)
        self.assertIn('./storage/theme:/www/storage/theme', result)
        self.assertIn('./plugins:/www/plugins', result)
        self.assertNotIn('./releases/', result)

    def test_refuses_unknown_theme_overrides(self):
        with self.assertRaisesRegex(RuntimeError, 'Unexpected theme'):
            release.release_compose('services:\n  xboard:\n    image: old\n    volumes:\n      - ./custom/index.html:/www/theme/Xboard/index.html:ro\n', 'new')

    def test_backup_has_consistent_live_sqlite_and_private_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory)
            (app / '.docker/.data').mkdir(parents=True)
            (app / 'compose.yaml').write_text('synthetic configuration')
            (app / '.env').write_text('synthetic test fixture')
            with closing(sqlite3.connect(app / '.docker/.data/database.sqlite')) as database:
                database.execute('PRAGMA journal_mode=WAL')
                database.execute('CREATE TABLE fixture (value TEXT)')
                database.execute("INSERT INTO fixture VALUES ('committed')")
                database.commit()
                with patch.object(release, 'APP', app), patch.object(release, 'COMPOSE', app / 'compose.yaml'):
                    checkpoint = release.backup('sha256:previous', 'a' * 40)
                with closing(sqlite3.connect(checkpoint / 'database.sqlite')) as copied:
                    self.assertEqual(copied.execute('SELECT value FROM fixture').fetchone(), ('committed',))
                self.assertEqual(checkpoint.stat().st_mode & 0o777, 0o700)
                for file in checkpoint.iterdir():
                    self.assertEqual(file.stat().st_mode & 0o777, 0o600)


class DeploymentSafety(unittest.TestCase):
    def test_health_accepts_grouped_supervisor_names_but_rejects_crashed_queue(self):
        target = 'd' * 40
        container = {'Image': 'sha256:expected', 'State': {'Status': 'running'},
                     'Config': {'Labels': {'org.opencontainers.image.revision': target}}, 'Mounts': []}
        processes = 'octane:octane_00 RUNNING\nhorizon:horizon_00 RUNNING\nredis RUNNING\ncaddy RUNNING\n'
        with patch.object(release, 'inspect', return_value=container), \
             patch.object(release, 'run', return_value=processes), \
             patch.object(release, 'verify_http') as verify:
            release.healthy(target, 'sha256:expected', 'https://example.invalid')
            self.assertEqual(verify.call_count, 2)
        with patch.object(release, 'inspect', return_value=container), \
             patch.object(release, 'run', return_value=processes.replace('horizon_00 RUNNING', 'horizon_00 BACKOFF')):
            with self.assertRaisesRegex(RuntimeError, 'horizon'):
                release.healthy(target, 'sha256:expected', 'https://example.invalid')

    def test_failed_post_restart_checks_restore_immutable_previous_image(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory)
            compose = app / 'compose.yaml'
            compose.write_text('services:\n  xboard:\n    image: mutable-current\n')
            target, old = 'b' * 40, 'a' * 40
            container = {'Image': 'sha256:old', 'State': {'Status': 'running'},
                         'Config': {'Labels': {'org.opencontainers.image.revision': old}}}
            args = type('Args', (), {'poll': False, 'sha': target, 'retry': False})()
            def fake_run(command, **kwargs):
                if command[:3] == ['docker', 'image', 'inspect']:
                    return json.dumps([{'Id': 'sha256:new', 'Config': {'Labels': {'org.opencontainers.image.revision': target}}}])
                return ''
            with patch.multiple(release, APP=app, COMPOSE=compose, STAGING_ROOT=app / 'staging'), \
                 patch.object(release, 'fetch_master', return_value=target), \
                 patch.object(release, 'inspect', return_value=container), \
                 patch.object(release, 'validate_target'), \
                 patch.object(release, 'git', return_value='app/change.php'), \
                 patch.object(release, 'public_url', return_value='https://example.invalid'), \
                 patch.object(release, 'get', return_value=b'healthy'), \
                 patch.object(release, 'save_state'), \
                 patch.object(release, 'run', side_effect=fake_run), \
                 patch.object(release, 'backup', return_value=app / 'checkpoint'), \
                 patch.object(release, 'compose_up') as restart, \
                 patch.object(release, 'healthy', side_effect=RuntimeError('bad release')), \
                 patch.object(release.time, 'sleep'), \
                 patch.object(release.subprocess, 'run') as process:
                # Archive extraction is isolated to a temporary directory; no production commands run.
                process.return_value.stdout = b''
                with self.assertRaisesRegex(RuntimeError, 'previous image and Compose restored'):
                    release.deploy(args)
                self.assertEqual(restart.call_count, 2)
                self.assertIn('image: sha256:old', compose.read_text())

    def test_health_requires_both_source_identity_and_public_assets(self):
        target = 'c' * 40
        page = '<title>筋斗云</title><script src="/theme/Xboard/assets/ez-theme/main.js"></script>'
        def response(url):
            if '/release.json' in url:
                return json.dumps({'revision': target}).encode()
            if 'release_check=' in url:
                return page.encode()
            raise RuntimeError('asset missing')
        with patch.object(release, 'get', side_effect=response):
            with self.assertRaisesRegex(RuntimeError, 'asset missing'):
                release.verify_http('https://example.invalid', target)
        with patch.object(release, 'get', return_value=b'{"revision":"wrong"}'):
            with self.assertRaisesRegex(RuntimeError, 'revision'):
                release.verify_http('https://example.invalid', target)


if __name__ == '__main__':
    unittest.main()
