"""G1.16 server boundary tests for runtime-issued Model Profile authority."""
from __future__ import annotations

import copy
import tempfile
import unittest
import sys
import json
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE / 'orchestrator'))
sys.path.insert(0, str(WORKSPACE / 'server'))

import conversation_memory as runtime_memory
import oversight_actions
import oversight_queue
import system_protection
import tool_events
from orchestrator import conversation_memory as package_memory
from orchestrator import active_configuration as ac
from orchestrator import model_profiles as mp
from orchestrator import project_meta as pm
from server import app as server


class _NoopThread:
    """Stub thread that fires no side-effects — mirrors test_visual_fallback.

    ``_persist_turn_spatial_state`` is dispatched on a daemon thread, so a
    real thread finishes after ``tearDown`` has restored the sessions root
    and writes the turn into the user's live store instead of the temp one.
    """

    def __init__(self, *a, **k):
        pass

    def start(self):
        pass

    def join(self, *a, **k):
        pass

    daemon = True


class ModelProfileApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.app.config.update(TESTING=True)
        cls.client = server.app.test_client()

    def setUp(self):
        # The /chat cases below drive the Flask client with real conversation
        # ids. Without an override they write conversation records into the
        # user's live sessions store and then read that state back, so a
        # record left closed by an earlier run answers 409 forever after.
        self._sessions_tmp = tempfile.TemporaryDirectory()
        self._sessions_stack = ExitStack()
        for module in (runtime_memory, package_memory):
            self._sessions_stack.enter_context(mock.patch.object(
                module, "_DEFAULT_SESSIONS_ROOT",
                Path(self._sessions_tmp.name),
            ))
        self._sessions_stack.enter_context(
            mock.patch.object(server.threading, "Thread", _NoopThread)
        )

    def tearDown(self):
        self._sessions_stack.close()
        self._sessions_tmp.cleanup()

    def test_configuration_inventory_rebake_reloads_router_after_write(self):
        events = []
        catalog = {
            'presets': {name: None for name in ac.PRESET_ORDER},
            'customs': [], 'active_name': 'free', 'active_toggles': {},
        }
        with (
            mock.patch.object(
                server, '_refresh_local_model_inventory',
                side_effect=lambda: (events.append('scan') or ({}, None)),
            ),
            mock.patch.object(
                ac, 'bake_missing_presets',
                side_effect=lambda *a, **k: (events.append('bake') or ['free']),
            ) as bake,
            mock.patch.object(
                server, '_reload_pipeline_router_after_config_change',
                side_effect=lambda: (events.append('reload') or True),
            ),
            mock.patch.object(ac, 'list_configurations', return_value=catalog),
            mock.patch.object(
                mp, 'decorate_configuration_catalog', side_effect=lambda value: value,
            ),
        ):
            response = self.client.get('/api/configurations')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(events, ['scan', 'bake', 'reload'])
        bake.assert_called_once_with(force=True, preset_names=('free',))

    def test_custom_profile_delete_requires_approval_and_succeeds_on_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            configurations = root / 'configurations'
            configurations.mkdir()
            profile_path = configurations / 'Approval Test.json'
            profile_path.write_text(json.dumps({
                'name': 'Approval Test',
                'preset_lineage': 'custom',
            }), encoding='utf-8')
            pointer_path = root / 'active-configuration.json'
            pointer_path.write_text(
                json.dumps({'name': 'free'}), encoding='utf-8')
            approvals_path = root / 'execution-approvals.json'
            events_path = root / 'tool-events.jsonl'
            queue_path = root / 'human-queue.jsonl'
            actions_path = root / 'actions.jsonl'

            tool_events._queued_hashes.clear()
            try:
                with (
                    mock.patch.object(ac, 'CONFIGURATIONS_DIR', configurations),
                    mock.patch.object(ac, 'ACTIVE_POINTER_PATH', pointer_path),
                    mock.patch.object(
                        tool_events, 'APPROVALS_PATH', str(approvals_path)),
                    mock.patch.object(
                        tool_events, 'GLOBAL_SINK_DEFAULT', str(events_path)),
                    mock.patch.object(
                        oversight_queue, 'HUMAN_QUEUE_PATH', str(queue_path)),
                    mock.patch.object(
                        oversight_actions, 'HUMAN_QUEUE_PATH', str(queue_path)),
                    mock.patch.object(
                        system_protection, '_actions_path',
                        return_value=str(actions_path),
                    ),
                ):
                    first = self.client.delete(
                        '/api/configurations/Approval%20Test')
                    first_payload = first.get_json()

                    self.assertEqual(first.status_code, 409, first_payload)
                    self.assertEqual(
                        first_payload['status'],
                        'awaiting_system_protection_approval',
                    )
                    self.assertTrue(first_payload['retry_required'])
                    self.assertTrue(profile_path.is_file())

                    entry = oversight_queue.find_paused_by_id(
                        first_payload['queue_id'])
                    self.assertIsNotNone(entry)
                    approved = tool_events.resolve_gate_entry(
                        entry.to_dict(), approve=True)
                    self.assertIn('One-shot token', approved)

                    retry = self.client.delete(
                        '/api/configurations/Approval%20Test')
                    self.assertEqual(
                        retry.status_code, 200, retry.get_json())
                    self.assertEqual(
                        retry.get_json(), {'deleted': 'Approval Test'})
                    self.assertFalse(profile_path.exists())
            finally:
                tool_events._queued_hashes.clear()

    def test_toggle_rebake_reloads_router_after_all_profile_writes(self):
        events = []
        with (
            mock.patch.object(
                ac, 'set_preset_toggles',
                side_effect=lambda body, **kwargs: (
                    events.append(('toggle_transaction', kwargs)) or body
                ),
            ),
            mock.patch.object(ac, 'get_active_name', return_value='custom'),
            mock.patch.object(
                ac, 'get_toggles', return_value={
                    'adversarial_diversity': True,
                    'vision_only': False,
                    'min_context_1m': False,
                },
            ),
            mock.patch.object(
                server, '_reload_pipeline_router_after_config_change',
                side_effect=lambda: (events.append('reload') or True),
            ),
        ):
            response = self.client.post(
                '/api/configurations/active/toggles',
                json={'adversarial_diversity': False},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(events, [
            ('toggle_transaction', {
                'rebake': True,
                'custom_profile_name': 'custom',
            }),
            'reload',
        ])

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

    def test_over_cap_project_binding_is_rejected_before_pointer_write(self):
        oversized = {
            'name': 'Oversized',
            'toggles': {'adversarial_diversity': False},
            'cells': {
                'utility': {'step1_cleanup': {
                    'primary': 'local-too-large', 'fallback': [],
                }},
                'analysis': {
                    'gear4': {'depth': {
                        'primary': 'local-too-large', 'fallback': [],
                    }},
                    'gear3': {'depth': {
                        'primary': 'local-too-large', 'fallback': [],
                    }},
                },
            },
        }
        with (
            mock.patch.object(mp, '_read_profile', return_value=oversized),
            mock.patch.object(mp.ac, '_get_system_ram_gb', return_value=100),
            mock.patch.object(mp.ac, '_load_local_models', return_value=[
                {'id': 'local-too-large', 'ram_gb': 86},
            ]),
            mock.patch.object(pm, 'set_project_model_binding') as persist,
        ):
            response = self.client.post('/api/model-profiles/project/example', json={
                'name': 'Oversized',
            })
        self.assertEqual(response.status_code, 400)
        self.assertIn('85% hard cap', response.get_json()['error'])
        persist.assert_not_called()

    def test_public_one_run_override_rejects_over_cap_profile_before_execution(self):
        with (
            mock.patch.object(mp, 'profile_summary', return_value={
                'health': {'status': 'ok', 'reason': ''},
            }),
            mock.patch.object(
                mp, 'validate_profile_allocation',
                side_effect=mp.ModelProfileError(
                    'Model Profile local RAM allocation exceeds the 85% hard cap'
                ),
            ),
            mock.patch.object(server, '_invoke_pipeline') as invoke,
        ):
            response = self.client.post('/chat', json={
                'message': 'Run once with this profile.',
                'panel_id': 'ram-one-run-rejection',
                'config_name': 'Oversized',
            })
        self.assertEqual(response.status_code, 400)
        self.assertIn('85% hard cap', response.get_json()['error'])
        invoke.assert_not_called()

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

    def test_direct_image_capability_keeps_shared_provider_result_contract(self):
        import capability_registry

        invocation = mock.Mock(provider_id='saved-provider', attempts=[])
        with mock.patch.object(
            server, '_active_project_model_locks', return_value=None,
        ), mock.patch.object(
            capability_registry, 'invoke_image_generation',
            return_value=(invocation, b'provider-image', 'image/webp', 'webp'),
        ) as invoke:
            response = self.client.post('/api/capability/image_generates', json={
                'slot': 'image_generates',
                'inputs': {'prompt': 'A test image'},
            })

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload['provider'], 'saved-provider')
        self.assertEqual(payload['image']['mime_type'], 'image/webp')
        self.assertEqual(invoke.call_args.kwargs['provider_id'], None)

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
        import framework_preflight as preflight
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
        current = {'process': None, 'step': None}
        invoked_endpoints = []
        saved_assistant = []

        def load_operative_framework(_canonical, _project_nexus):
            raw = dedent('''\
                # Public Gear 2 profile proof

                ## MILESTONES DELIVERED

                ### Milestone 1: Result
                - **Endpoint produced:** A result.
                - **Verification criterion:** It exists.
                - **Methods:** work
                - **Required prior milestones:** None
                - **External prerequisites:** None
                - **Gear:** 2
                - **Output format:** Markdown.
                - **Drift check question:** Is it complete?

                ## EXECUTION METHODS

                ### METHOD work: Produce the result
                Produce the requested result.
            ''')
            if current['step']:
                raw = raw.replace(
                    '- **Output format:** Markdown.',
                    f"- **Model Profile:** {current['step']}\n"
                    '- **Output format:** Markdown.',
                )
            return raw, 'public-gear2-profile-proof.md', None

        def slot_endpoint(_config, slot, *, config_name=None, **_kwargs):
            self.assertEqual(slot, 'fast')
            return {'id': f'endpoint::{config_name}'}

        def run_model(_messages, endpoint, **_kwargs):
            invoked_endpoints.append(endpoint['id'])
            return 'Framework result with sufficient material detail.'

        def save_conversation(_user, assistant, *_args, **_kwargs):
            saved_assistant.append(assistant)
            return 'chunk-g116-gear2'

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
            mock.patch.object(server, '_log_pending_submission', return_value=None),
            mock.patch.object(server, '_finalize_pending_submission'),
            mock.patch.object(
                server, '_save_conversation', side_effect=save_conversation),
            mock.patch.object(server, 'build_contributor_context', return_value=None),
            mock.patch.object(server, 'RUNTIME_PIPELINE_AVAILABLE', False),
            mock.patch.object(server, '_session_data', {}),
            mock.patch.object(
                preflight, '_load_bound_text', side_effect=load_operative_framework),
            mock.patch.object(
                preflight, '_lookup_process_profile',
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
                    self.assertTrue(
                        invoked_endpoints,
                        saved_assistant[-1] if saved_assistant else
                        response.get_data(as_text=True),
                    )
                    self.assertEqual(invoked_endpoints[-1], f'endpoint::{expected}')

        self.assertEqual(
            invoked_endpoints,
            [f'endpoint::{case[-1]}' for case in cases],
        )


if __name__ == '__main__':
    unittest.main()
