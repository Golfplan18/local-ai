"""G1.16 server boundary tests for runtime-issued Model Profile authority."""
from __future__ import annotations

import unittest
import sys
from pathlib import Path
from unittest import mock

WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE / 'server'))

from orchestrator import model_profiles as mp
from orchestrator import project_meta as pm
import server


class ModelProfileApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.app.config.update(TESTING=True)
        cls.client = server.app.test_client()

    def test_generic_project_patch_rejects_browser_supplied_locks(self):
        response = self.client.post('/api/projects/example', json={
            'model_locks': {'profile_snapshot': {'forged': True}},
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('runtime-authenticated', response.get_json()['error'])

    def test_project_profile_endpoint_issues_the_lock_server_side(self):
        locks = {'binding_digest': 'server-issued'}
        record = {
            'nexus': 'example', 'default_model_profile': 'Balanced',
            'model_locks': locks,
        }
        effective = {'selected': {'name': 'Balanced', 'source': 'project'}}
        with (
            mock.patch.object(mp, 'capture_project_binding', return_value=locks) as capture,
            mock.patch.object(pm, 'set_project_model_binding', return_value=record) as persist,
            mock.patch.object(mp, 'resolve_effective_profile', return_value=effective),
        ):
            response = self.client.post('/api/model-profiles/project/example', json={
                'name': 'Balanced',
                'model_locks': {'binding_digest': 'browser-forged'},
            })
        self.assertEqual(response.status_code, 200)
        capture.assert_called_once_with('Balanced')
        persist.assert_called_once_with('example', 'Balanced', locks)
        self.assertEqual(response.get_json()['effective'], effective)

    def test_legacy_project_update_also_captures_an_exact_binding(self):
        locks = {'binding_digest': 'server-issued'}
        with (
            mock.patch.object(mp, 'capture_project_binding', return_value=locks),
            mock.patch.object(pm, 'set_project_model_binding', return_value={
                'nexus': 'example', 'default_model_profile': 'Balanced',
                'model_locks': locks,
            }) as persist,
        ):
            response = self.client.post('/api/projects/example', json={
                'default_model_profile': 'Balanced', 'status': 'active',
            })
        self.assertEqual(response.status_code, 200)
        persist.assert_called_once_with(
            'example', 'Balanced', locks, updates={'status': 'active'})

    def test_migration_confirmation_cannot_be_implicit(self):
        with mock.patch.object(mp, 'confirm_migration', wraps=mp.confirm_migration):
            response = self.client.post('/api/model-profiles/migration/confirm', json={
                'name': 'Legacy', 'proposal_id': 'a' * 64,
            })
        self.assertEqual(response.status_code, 409)
        self.assertIn('explicit migration confirmation', response.get_json()['error'])

    def test_project_image_lock_cannot_be_overridden_by_request(self):
        with mock.patch.object(server, '_active_project_model_locks', return_value={
            'image_model': 'locked-image-provider',
        }):
            response = self.client.post('/api/capability/image_generates', json={
                'slot': 'image_generates',
                'provider_override': 'different-provider',
                'inputs': {'prompt': 'A test image'},
            })
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.get_json()['error']['code'],
            'model_profile_image_lock_conflict',
        )

    def test_runtime_project_token_is_not_a_public_one_run_override(self):
        with self.assertRaisesRegex(mp.ModelProfileError, 'not public'):
            server._validate_public_model_profile_override(
                'project-lock:example:' + ('a' * 64))

    def test_both_public_chat_surfaces_reject_runtime_project_tokens(self):
        token = 'project-lock:example:' + ('a' * 64)
        json_response = self.client.post('/chat', json={
            'message': 'test', 'panel_id': 'main', 'config_name': token,
        })
        multipart_response = self.client.post('/chat/multipart', data={
            'message': 'test', 'conversation_id': 'main',
            'panel_id': 'main', 'config_name': token,
        })
        self.assertEqual(json_response.status_code, 400)
        self.assertEqual(multipart_response.status_code, 400)
        self.assertIn('not public', json_response.get_json()['error'])
        self.assertIn('not public', multipart_response.get_json()['error'])

    def test_unavailable_public_one_run_override_fails_closed(self):
        with mock.patch.object(mp, 'profile_summary', return_value={
            'health': {'status': 'unavailable', 'reason': 'no endpoint'},
        }):
            with self.assertRaisesRegex(mp.ModelProfileError, 'unavailable'):
                server._validate_public_model_profile_override('Offline')


if __name__ == '__main__':
    unittest.main()
