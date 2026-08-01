"""G1.16 server boundary tests for runtime-issued Model Profile authority."""
from __future__ import annotations

import copy
import unittest
import sys
import json
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE / 'server'))

from orchestrator import model_profiles as mp
from orchestrator import project_meta as pm
from server import app as server


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
        capture.assert_called_once_with('Balanced', 'example')
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

    def test_public_chat_framework_path_passes_project_and_toolbar_override(self):
        import milestone_executor as executor
        import model_profiles as top_mp
        import framework_parser as top_parser
        import boot
        from textwrap import dedent

        profile = {
            'cells': {
                'utility': {
                    'step1_cleanup': {'primary': 'model-ok', 'fallback': []},
                },
                'analysis': {
                    'gear3': {
                        'depth': {'primary': 'model-ok', 'fallback': []},
                    },
                    'gear4': {
                        'depth': {'primary': 'model-ok', 'fallback': []},
                    },
                },
            },
            'toggles': {'adversarial_diversity': False},
        }
        locks = {
            'schema_version': top_mp.LOCK_SCHEMA_VERSION,
            'project_nexus': 'example',
            'profile_name': 'Project Profile',
            'profile_digest': top_mp.profile_digest(profile),
            'profile_snapshot': profile,
            'toggles': {'adversarial_diversity': False},
            'image_model': 'locked-image',
            'vision_mode': {
                'vision_extraction': {'enabled': False, 'mode': 'locked'},
            },
            'captured_at': '2026-07-22T00:00:00+00:00',
        }
        locks['binding_digest'] = top_mp._binding_digest(locks)
        record = {
            'nexus': 'example', 'default_model_profile': 'Project Profile',
            'model_locks': locks,
        }
        framework = top_parser.parse_framework_text(dedent('''\
            # Public profile proof

            ## LAYER 1: Work
            Produce the result.

            ## MILESTONES DELIVERED

            ### Milestone 1: Result
            - **Endpoint produced:** A result.
            - **Verification criterion:** It exists.
            - **Layers covered:** 1
            - **Required prior milestones:** None
            - **Gear:** 4
            - **Model Profile:** Step Profile
            - **Output format:** Markdown.
            - **Drift check question:** Is it complete?
        '''), path='public-profile-proof.md')
        observed = {}
        resolutions = []
        original_resolve = executor._resolve_milestone_model_profile

        def resolve(**kwargs):
            result = original_resolve(**kwargs)
            resolutions.append(result)
            return result

        def run_gear4(context_pkg, _config, config_name=None, **_kwargs):
            observed['config_name'] = config_name
            observed['context_pkg'] = context_pkg
            return 'framework result'

        def save_conversation(_user, assistant, *_args, **_kwargs):
            observed['assistant'] = assistant
            return 'chunk-g116'

        with (
            mock.patch.object(boot, 'PIPELINE_TRACE_AVAILABLE', False),
            mock.patch.object(server, 'load_config', return_value={}),
            mock.patch.object(server, 'get_endpoint', return_value={'name': 'test'}),
            mock.patch.object(
                server, '_validate_public_model_profile_override',
                return_value='Toolbar Profile',
            ),
            mock.patch.object(
                server, '_active_project_model_context',
                return_value=('example', locks),
            ),
            mock.patch.object(server, '_log_pending_submission', return_value='sub-g116'),
            mock.patch.object(server, '_finalize_pending_submission'),
            mock.patch.object(server, '_save_conversation', side_effect=save_conversation),
            mock.patch.object(server, 'build_contributor_context', return_value=None),
            mock.patch.object(server, 'RUNTIME_PIPELINE_AVAILABLE', False),
            mock.patch.object(executor, 'parse_framework_file', return_value=framework),
            mock.patch.object(
                executor, '_lookup_framework_default_configuration',
                return_value='Process Profile',
            ),
            mock.patch.object(
                executor, '_resolve_milestone_model_profile', side_effect=resolve,
            ),
            mock.patch.object(
                executor, '_run_drift_check', return_value=('IN_SCOPE', 'verified'),
            ),
            mock.patch.object(top_mp.pm, 'read_project_meta', return_value=record),
            mock.patch.object(top_mp, '_read_profile', return_value=profile),
            mock.patch.object(top_mp.ac, 'get_active_name', return_value='Global Profile'),
            mock.patch.object(top_mp, 'load_model_inventory', return_value={
                'models': {'model-ok': {'reachable': True}},
                'aliases': {}, 'routing': {},
            }),
            mock.patch.object(boot, 'run_gear4', side_effect=run_gear4),
        ):
            response = self.client.post('/chat', json={
                'message': '/framework cff summarize this repository',
                'panel_id': 'g116-public-path',
                'conversation_id': 'g116-public-path',
                'config_name': 'Toolbar Profile',
                'history': [],
            })
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(json.loads(response.get_data(as_text=True))['status'], 'ok')
        self.assertIn('framework result', observed.get('assistant', ''), observed)
        self.assertEqual(observed['config_name'], 'Toolbar Profile')
        self.assertEqual(observed['context_pkg']['model_profile_locks'], locks)
        self.assertEqual(len(resolutions), 1)
        self.assertEqual(
            [row['source'] for row in resolutions[0]['chain']],
            ['global', 'project', 'process', 'step', 'one_run'],
        )

    def test_public_chat_gear2_invokes_each_effective_profile_endpoint(self):
        import milestone_executor as executor
        import model_profiles as top_mp
        import framework_parser as top_parser
        import boot
        from textwrap import dedent

        profile = {
            'cells': {
                'utility': {
                    'step1_cleanup': {'primary': 'model-ok', 'fallback': []},
                },
                'analysis': {
                    'gear3': {
                        'depth': {'primary': 'model-ok', 'fallback': []},
                    },
                    'gear4': {
                        'depth': {'primary': 'model-ok', 'fallback': []},
                    },
                },
            },
            'toggles': {'adversarial_diversity': False},
        }
        locks = {
            'schema_version': top_mp.LOCK_SCHEMA_VERSION,
            'project_nexus': 'example',
            'profile_name': 'Project Profile',
            'profile_digest': top_mp.profile_digest(profile),
            'profile_snapshot': profile,
            'toggles': {'adversarial_diversity': False},
            'image_model': 'locked-image',
            'vision_mode': {
                'vision_extraction': {'enabled': False, 'mode': 'locked'},
            },
            'captured_at': '2026-07-22T00:00:00+00:00',
        }
        locks['binding_digest'] = top_mp._binding_digest(locks)
        record = {
            'nexus': 'example', 'default_model_profile': 'Project Profile',
            'model_locks': locks,
        }
        project_token = top_mp.project_lock_token('example', locks)
        base_framework = top_parser.parse_framework_text(dedent('''\
            # Public Gear 2 profile proof

            ## LAYER 1: Work
            Produce the result.

            ## MILESTONES DELIVERED

            ### Milestone 1: Result
            - **Endpoint produced:** A result.
            - **Verification criterion:** It exists.
            - **Layers covered:** 1
            - **Required prior milestones:** None
            - **Gear:** 2
            - **Output format:** Markdown.
            - **Drift check question:** Is it complete?
        '''), path='public-gear2-profile-proof.md')
        current = {'process': None, 'step': None}
        invoked_endpoints = []

        def parsed_framework(_path):
            framework = copy.deepcopy(base_framework)
            framework.all_milestones()[0].model_profile = current['step']
            return framework

        def slot_endpoint(_config, slot, *, config_name=None, **_kwargs):
            self.assertEqual(slot, 'fast')
            return {'id': f'endpoint::{config_name}'}

        def run_model(_messages, endpoint, **_kwargs):
            invoked_endpoints.append(endpoint['id'])
            return 'framework result'

        cases = (
            ('project', None, None, None, project_token),
            ('process', 'Process Profile', None, None, 'Process Profile'),
            ('step', 'Process Profile', 'Step Profile', None, 'Step Profile'),
            (
                'one-run', 'Process Profile', 'Step Profile',
                'Toolbar Profile', 'Toolbar Profile',
            ),
        )

        patchers = (
            mock.patch.object(boot, 'PIPELINE_TRACE_AVAILABLE', False),
            mock.patch.object(server, 'load_config', return_value={}),
            mock.patch.object(server, 'get_endpoint', return_value={'name': 'test'}),
            mock.patch.object(
                server, '_validate_public_model_profile_override',
                side_effect=lambda value: value,
            ),
            mock.patch.object(
                server, '_active_project_model_context',
                return_value=('example', locks),
            ),
            mock.patch.object(server, '_log_pending_submission', return_value='sub-g116'),
            mock.patch.object(server, '_finalize_pending_submission'),
            mock.patch.object(
                server, '_save_conversation', return_value='chunk-g116-gear2'),
            mock.patch.object(server, 'build_contributor_context', return_value=None),
            mock.patch.object(server, 'RUNTIME_PIPELINE_AVAILABLE', False),
            mock.patch.object(server, '_session_data', {}),
            mock.patch.object(
                executor, 'parse_framework_file', side_effect=parsed_framework),
            mock.patch.object(
                executor, '_lookup_framework_default_configuration',
                side_effect=lambda _name: current['process'],
            ),
            mock.patch.object(
                executor, '_run_drift_check', return_value=('IN_SCOPE', 'verified'),
            ),
            mock.patch.object(top_mp.pm, 'read_project_meta', return_value=record),
            mock.patch.object(top_mp, '_read_profile', return_value=profile),
            mock.patch.object(top_mp.ac, 'get_active_name', return_value='Global Profile'),
            mock.patch.object(top_mp, 'load_model_inventory', return_value={
                'models': {'model-ok': {'reachable': True}},
                'aliases': {}, 'routing': {},
            }),
            mock.patch.object(boot, 'get_slot_endpoint', side_effect=slot_endpoint),
            mock.patch.object(
                boot, 'get_active_endpoint',
                side_effect=AssertionError(
                    'public Gear-2 execution used the global endpoint'),
            ),
            mock.patch.object(
                boot, '_run_model_with_tools', side_effect=run_model),
        )
        with ExitStack() as stack:
            for patcher in patchers:
                stack.enter_context(patcher)
            for index, (label, process, step, one_run, expected) in enumerate(cases):
                with self.subTest(level=label):
                    current.update(process=process, step=step)
                    response = self.client.post('/chat', json={
                        'message': '/framework cff summarize this repository',
                        'panel_id': f'g116-gear2-{index}',
                        'conversation_id': f'g116-gear2-{index}',
                        'config_name': one_run,
                        'is_main_feed': False,
                        'history': [],
                    })
                    self.assertEqual(
                        response.status_code, 200,
                        response.get_data(as_text=True),
                    )
                    self.assertEqual(
                        json.loads(response.get_data(as_text=True))['status'], 'ok')
                    self.assertEqual(invoked_endpoints[-1], f'endpoint::{expected}')

        self.assertEqual(
            invoked_endpoints,
            [f'endpoint::{case[-1]}' for case in cases],
        )


if __name__ == '__main__':
    unittest.main()
