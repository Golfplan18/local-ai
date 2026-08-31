"""Provider-returned URL and bearer-origin boundary tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

_ORCH = Path(__file__).resolve().parent.parent
if str(_ORCH) not in sys.path:
    sys.path.insert(0, str(_ORCH))
_INTEGRATIONS = _ORCH / "integrations"
if str(_INTEGRATIONS) not in sys.path:
    sys.path.insert(0, str(_INTEGRATIONS))
_TESTS = str(Path(__file__).resolve().parent)
if _TESTS not in sys.path:
    sys.path.insert(0, _TESTS)
import live_guard  # noqa: E402,F401

import network_policy  # noqa: E402
import openrouter_images  # noqa: E402
from orchestrator.integrations import replicate as replicate_images  # noqa: E402


def _context_manager(value):
    manager = mock.MagicMock()
    manager.__enter__.return_value = value
    manager.__exit__.return_value = False
    return manager


def _public_dns(_host, port, **_kwargs):
    return [
        (network_policy.socket.AF_INET, network_policy.socket.SOCK_STREAM,
         6, "", ("93.184.216.34", port)),
    ]


def _openrouter_sdk_fakes(response):
    client = mock.Mock()
    client.chat.completions.create.return_value = response
    constructor = mock.Mock(return_value=client)
    transport = mock.Mock()
    manager = mock.Mock()
    manager.__enter__ = mock.Mock(return_value=transport)
    manager.__exit__ = mock.Mock(return_value=False)
    transport_factory = mock.Mock(return_value=manager)
    modules = {
        "openai": types.SimpleNamespace(OpenAI=constructor),
        "httpx": types.SimpleNamespace(Client=transport_factory),
    }
    return client, constructor, transport, transport_factory, modules


class TestOpenRouterNetworkBoundary(unittest.TestCase):
    def test_image_sdk_transport_refuses_redirects(self):
        response = types.SimpleNamespace(choices=[types.SimpleNamespace(
            message=types.SimpleNamespace(images=[{
                "image_url": {"url": "data:image/png;base64,YQ=="},
            }]),
        )])
        client, constructor, transport, transport_factory, modules = (
            _openrouter_sdk_fakes(response)
        )
        with mock.patch.object(openrouter_images, "_resolve_key", return_value="bearer"), \
             mock.patch.object(
                 openrouter_images, "_with_image_deadline",
                 side_effect=lambda call: call(),
             ), mock.patch.dict(sys.modules, modules):
            result = openrouter_images._call_image_model("vendor/model", "draw")
        self.assertEqual(result, b"a")
        kwargs = transport_factory.call_args.kwargs
        self.assertIs(kwargs["follow_redirects"], False)
        self.assertEqual(
            kwargs["event_hooks"]["request"],
            [openrouter_images._validate_openrouter_request],
        )
        self.assertIs(constructor.call_args.kwargs["http_client"], transport)

    def test_two_image_style_path_uses_same_origin_locked_transport(self):
        response = types.SimpleNamespace(choices=[types.SimpleNamespace(
            message=types.SimpleNamespace(images=[{
                "image_url": {"url": "data:image/png;base64,YQ=="},
            }]),
        )])
        client, constructor, transport, transport_factory, modules = (
            _openrouter_sdk_fakes(response)
        )
        with mock.patch.object(openrouter_images, "_resolve_key", return_value="bearer"), \
             mock.patch.object(
                 openrouter_images, "_with_image_deadline",
                 side_effect=lambda call: call(),
             ), mock.patch.dict(sys.modules, modules):
            result = openrouter_images._call_image_model_two_images(
                "vendor/model", "restyle", b"source", b"style",
            )
        self.assertEqual(result, b"a")
        self.assertEqual(client.chat.completions.create.call_count, 1)
        self.assertIs(constructor.call_args.kwargs["http_client"], transport)
        self.assertIs(
            transport_factory.call_args.kwargs["follow_redirects"], False,
        )

    def test_sdk_request_hook_refuses_cross_origin_before_send(self):
        request = types.SimpleNamespace(url="https://evil.example/steal")
        with mock.patch.object(
            openrouter_images.network_policy.socket, "getaddrinfo",
            side_effect=_public_dns,
        ):
            with self.assertRaises(
                openrouter_images.network_policy.NetworkPolicyError,
            ):
                openrouter_images._validate_openrouter_request(request)

    def test_image_result_uses_public_asset_transport_without_bearer(self):
        with mock.patch.object(
            openrouter_images.network_policy, "urllib_request_bytes",
            return_value=(b"image", mock.sentinel.destination),
        ) as fetch:
            result = openrouter_images._decode_image_url_to_bytes(
                "https://cdn.example/image.png?sig=secret",
            )
        self.assertEqual(result, b"image")
        fetch.assert_called_once_with(
            "https://cdn.example/image.png?sig=secret", timeout=60,
        )

    def test_video_bearer_is_origin_bound_and_absent_from_asset(self):
        calls = []
        responses = [
            json.dumps({
                "id": "job-1",
                "polling_url": "https://openrouter.ai/api/v1/videos/job-1",
            }).encode(),
            json.dumps({
                "status": "completed",
                "unsigned_urls": ["https://cdn.example/video.mp4?sig=secret"],
            }).encode(),
            b"video",
        ]

        def fetch(url, **kwargs):
            calls.append((url, kwargs))
            return responses.pop(0), mock.sentinel.destination

        with mock.patch.object(openrouter_images, "_resolve_key", return_value="bearer"), \
             mock.patch.object(openrouter_images.time, "sleep", return_value=None), \
             mock.patch.object(
                 openrouter_images.network_policy,
                 "urllib_request_bytes",
                 side_effect=fetch,
             ):
            result = openrouter_images._call_video_model(
                "vendor/model", "prompt", poll_interval_s=0, max_wait_s=10,
            )
        self.assertEqual(result, b"video")
        for _url, kwargs in calls[:2]:
            self.assertEqual(kwargs["required_origin"], "https://openrouter.ai")
            self.assertIn("Authorization", kwargs["headers"])
            self.assertEqual(kwargs["max_redirects"], 0)
        asset_url, asset_kwargs = calls[2]
        self.assertEqual(asset_url, "https://cdn.example/video.mp4?sig=secret")
        self.assertNotIn("headers", asset_kwargs)
        self.assertNotIn("required_origin", asset_kwargs)

    def test_authenticated_cross_origin_is_refused_before_transport(self):
        opener = mock.Mock()
        with mock.patch.object(
            network_policy.socket, "getaddrinfo",
            return_value=[
                (network_policy.socket.AF_INET,
                 network_policy.socket.SOCK_STREAM, 6, "",
                 ("93.184.216.34", 443)),
            ],
        ):
            with self.assertRaises(network_policy.NetworkPolicyError):
                network_policy.urllib_request_bytes(
                    "https://evil.example/poll",
                    headers={"Authorization": "Bearer secret"},
                    required_origin="https://openrouter.ai",
                    opener=opener,
                )
        opener.open.assert_not_called()


class TestOpenRouterRuntimeCallers(unittest.TestCase):
    def test_embedding_and_reranker_use_the_origin_locked_transport(self):
        from orchestrator import embedding, reranker

        embedding_reply = json.dumps({
            "data": [
                {"index": 1, "embedding": [0.75, 0.25]},
                {"index": 0, "embedding": [0.25, 0.75]},
            ],
        }).encode()
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "secret"}), \
             mock.patch.object(
                 embedding.network_policy, "openrouter_request_bytes",
                 return_value=(embedding_reply, mock.sentinel.destination),
            ) as embedding_fetch:
            vectors = embedding._openrouter_embed_batch(
                ["hello", "world"], model="vendor/embed", attempts=1, dim=2,
            )
        self.assertEqual(vectors, [[0.25, 0.75], [0.75, 0.25]])
        self.assertEqual(
            embedding_fetch.call_args.args[0],
            "https://openrouter.ai/api/v1/embeddings",
        )
        self.assertEqual(
            embedding_fetch.call_args.kwargs["headers"]["Authorization"],
            "Bearer secret",
        )

        rerank_reply = json.dumps({
            "results": [{"index": 0, "relevance_score": 0.9}],
        }).encode()
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "secret"}), \
             mock.patch.object(
                 reranker.network_policy, "openrouter_request_bytes",
                 return_value=(rerank_reply, mock.sentinel.destination),
             ) as rerank_fetch:
            rows, metadata = reranker._call_openrouter(
                query="hello", documents=["world"], model="vendor/rerank",
                base_url="https://openrouter.ai/api/v1", top_n=1,
            )
        self.assertEqual(rows, [{"index": 0, "score": 0.9}])
        self.assertEqual(metadata["provider"], "openrouter")
        self.assertEqual(
            rerank_fetch.call_args.args[0],
            "https://openrouter.ai/api/v1/rerank",
        )

    def test_embedding_refuses_invalid_response_indices(self):
        from orchestrator import embedding

        def row(index):
            return {"index": index, "embedding": [0.25, 0.75]}

        valid = row(1)
        cases = {
            "row-not-object": [row(0), []],
            "index-absent": [{"embedding": [0.25, 0.75]}, valid],
            "bool-index": [row(False), valid],
            "string-index": [row("0"), valid],
            "float-index": [row(0.0), valid],
            "negative-index": [row(-1), valid],
            "duplicate-index": [row(0), row(0)],
            "missing-index": [row(0)],
            "out-of-range-index": [row(0), row(2)],
        }
        for name, rows in cases.items():
            with self.subTest(name=name), \
                 mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "secret"}), \
                 mock.patch.object(
                     embedding.network_policy, "openrouter_request_bytes",
                     return_value=(
                         json.dumps({"data": rows}).encode(),
                         mock.sentinel.destination,
                     ),
                 ), self.assertRaises(RuntimeError):
                embedding._openrouter_embed_batch(
                    ["hello", "world"], model="vendor/embed", attempts=1, dim=2,
                )

    def test_embedding_refuses_unsafe_vectors_before_upsert(self):
        from orchestrator import embedding

        cases = {
            "not-list": "unsafe",
            "bool-component": [True, 0.75],
            "string-component": ["0.25", 0.75],
            "null-component": [None, 0.75],
            "nan-component": [float("nan"), 0.75],
            "infinite-component": [float("inf"), 0.75],
            "wrong-dimension": [0.25],
        }
        for name, vector in cases.items():
            upsert = mock.Mock()
            reply = json.dumps({
                "data": [{"index": 0, "embedding": vector}],
            }).encode()
            with self.subTest(name=name), \
                 mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "secret"}), \
                 mock.patch.object(
                     embedding.network_policy, "openrouter_request_bytes",
                     return_value=(reply, mock.sentinel.destination),
                 ), self.assertRaises(RuntimeError):
                upsert(embeddings=embedding._openrouter_embed_batch(
                    ["hello"], model="vendor/embed", attempts=1, dim=2,
                ))
            upsert.assert_not_called()

    def test_embedding_refuses_nonofficial_base_before_transport(self):
        from orchestrator import embedding

        opener = mock.Mock()
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "secret"}), \
             mock.patch.object(network_policy.urllib.request, "build_opener", return_value=opener), \
             mock.patch.object(
                 network_policy.socket, "getaddrinfo", side_effect=_public_dns,
            ), self.assertRaisesRegex(RuntimeError, "trusted origin"):
            embedding._openrouter_embed_batch(
                ["hello"], model="vendor/embed",
                base_url="https://evil.example/api/v1", attempts=1, dim=2,
            )
        opener.open.assert_not_called()

    def test_chat_boot_uses_the_shared_sdk_boundary(self):
        from orchestrator import boot

        response = types.SimpleNamespace(
            choices=[types.SimpleNamespace(
                message=types.SimpleNamespace(
                    content="answer", tool_calls=None, refusal=None,
                ),
                finish_reason="stop",
            )],
            usage=None,
        )
        client = mock.Mock()
        client.chat.completions.create.return_value = response
        manager = _context_manager(client)
        endpoint = {
            "service": "openrouter",
            "model": "vendor/model",
            "context_window": 4096,
            "max_output_tokens": 64,
            "_disable_truncation_retry": True,
        }
        with mock.patch.object(
            boot, "_canonical_provider_key", return_value="secret",
        ), mock.patch.object(
            boot, "_vendor_catalog_authoritative", return_value=True,
        ), mock.patch.object(
            boot._network_policy, "openrouter_sdk_client",
            return_value=manager,
        ) as sdk:
            result = boot._call_api_endpoint_inner(
                [{"role": "user", "content": "hello"}], endpoint,
            )
        self.assertEqual(result, "answer")
        sdk.assert_called_once_with("secret")
        self.assertEqual(
            client.chat.completions.create.call_args.kwargs["model"],
            "vendor/model",
        )

    def test_transcription_paths_use_the_shared_sdk_boundary(self):
        from orchestrator import transcription

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "sample.wav"
            source.write_bytes(b"audio")
            manager = transcription.TranscriptionManager()

            transcript_client = mock.Mock()
            transcript_client.audio.transcriptions.create.return_value = (
                types.SimpleNamespace(text="hello", language="en", duration=1.5)
            )
            transcript_job = transcription._Transcription(
                "stt", source, {"openrouter_model": "vendor/stt"},
            )
            with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "secret"}), \
                 mock.patch.dict(sys.modules, {
                     "openai": types.SimpleNamespace(OpenAI=object),
                 }), mock.patch.object(
                     transcription.network_policy, "openrouter_sdk_client",
                     return_value=_context_manager(transcript_client),
                 ) as sdk:
                manager._run_openrouter(transcript_job)
            self.assertEqual(transcript_job.state, transcription.STATE_COMPLETE)
            self.assertEqual(transcript_job.plain_text, "hello")
            sdk.assert_called_once_with(
                "secret",
                timeout=transcription.REMOTE_REQUEST_TIMEOUT_SECONDS,
                max_retries=transcription.REMOTE_MAX_RETRIES,
            )

            audio_client = mock.Mock()
            audio_client.chat.completions.create.return_value = types.SimpleNamespace(
                choices=[types.SimpleNamespace(
                    message=types.SimpleNamespace(content="summary"),
                )],
            )
            audio_job = transcription._Transcription(
                "audio", source,
                {"openrouter_audio_model": "vendor/audio"},
            )
            with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "secret"}), \
                 mock.patch.dict(sys.modules, {
                     "openai": types.SimpleNamespace(OpenAI=object),
                 }), mock.patch.object(
                     transcription.network_policy, "openrouter_sdk_client",
                     return_value=_context_manager(audio_client),
                 ) as sdk:
                manager._run_openrouter_audio(audio_job)
            self.assertEqual(audio_job.state, transcription.STATE_COMPLETE)
            self.assertEqual(audio_job.plain_text, "summary")
            sdk.assert_called_once_with(
                "secret",
                timeout=transcription.REMOTE_REQUEST_TIMEOUT_SECONDS,
                max_retries=transcription.REMOTE_MAX_RETRIES,
            )

    def test_tts_and_key_verification_use_shared_boundaries(self):
        from server import app as server_app

        client = mock.Mock()
        client.audio.speech.create.return_value.read.return_value = b"mp3"
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "secret"}), \
             mock.patch.dict(sys.modules, {
                 "openai": types.SimpleNamespace(OpenAI=object),
             }), mock.patch.object(
                 server_app.network_policy, "openrouter_sdk_client",
                 return_value=_context_manager(client),
             ) as sdk:
            audio, mime = server_app._tts_openrouter(
                "hello", "vendor/tts", "voice",
            )
        self.assertEqual((audio, mime), (b"mp3", "audio/mpeg"))
        sdk.assert_called_once_with("secret")

        with mock.patch.object(
            server_app.network_policy, "openrouter_request_bytes",
            return_value=(b"{}", mock.sentinel.destination),
        ) as request_bytes:
            ok, _message = server_app._verify_provider_key(
                {"id": "openrouter"}, "secret",
            )
        self.assertIs(ok, True)
        request_bytes.assert_called_once_with(
            "https://openrouter.ai/api/v1/key",
            headers={"Authorization": "Bearer secret"},
            timeout=12,
            max_bytes=2 * 1024 * 1024,
        )

    def test_registry_probe_sdk_is_origin_locked_and_nonredirecting(self):
        from scripts import sync_model_registry

        transport = mock.sentinel.transport
        transport_factory = mock.Mock(return_value=transport)
        sdk_client = mock.sentinel.sdk_client
        sdk_factory = mock.Mock(return_value=sdk_client)
        modules = {
            "httpx": types.SimpleNamespace(Client=transport_factory),
            "openai": types.SimpleNamespace(OpenAI=sdk_factory),
        }
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "secret"}), \
             mock.patch.dict(sys.modules, modules):
            result = sync_model_registry._load_openrouter_client()
        self.assertIs(result, sdk_client)
        self.assertIs(
            transport_factory.call_args.kwargs["follow_redirects"], False,
        )
        self.assertEqual(
            transport_factory.call_args.kwargs["event_hooks"]["request"],
            [sync_model_registry.network_policy.validate_openrouter_request],
        )
        self.assertEqual(
            sdk_factory.call_args.kwargs["base_url"],
            sync_model_registry.network_policy.OPENROUTER_API_BASE,
        )
        self.assertIs(sdk_factory.call_args.kwargs["http_client"], transport)


class TestReplicateAssetBoundary(unittest.TestCase):
    def test_server_asset_helper_uses_shared_policy_transport(self):
        # Import after the hermetic live guard has established runtime roots.
        from server import app as server_app

        with mock.patch.object(
            server_app.network_policy, "urllib_request_bytes",
            return_value=(b"asset", mock.sentinel.destination),
        ) as fetch:
            result = server_app._fetch_provider_asset(
                "https://replicate.delivery/output.png", timeout=12,
            )
        self.assertEqual(result, b"asset")
        fetch.assert_called_once_with(
            "https://replicate.delivery/output.png", timeout=12,
        )

    def test_materialized_job_artifact_route_serves_only_owned_result(self):
        from server import app as server_app

        queue = server_app._get_job_queue()
        conversation_id = "replicate-artifact-route"
        job = queue.dispatch(
            conversation_id=conversation_id,
            capability="video_generates",
            parameters={},
        )
        uploads = server_app.rp.safe_owned_subdir(
            server_app.rp.ORA_HOME,
            "sessions", conversation_id, "uploads", create=True,
        )
        filename = f"replicate-{job['id']}-0.mp4"
        server_app.rp.atomic_write_bytes(uploads / filename, b"video")
        route = (
            f"/api/jobs/{conversation_id}/{job['id']}/artifacts/{filename}"
        )
        queue.mark_in_progress(conversation_id, job["id"])
        queue.mark_complete(
            conversation_id, job["id"], {"video_url": route},
        )
        client = server_app.app.test_client()
        response = client.get(route)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"video")
        refused = client.get(route.rsplit("/", 1)[0] + "/other.mp4")
        self.assertEqual(refused.status_code, 404)

    def test_all_authenticated_replicate_calls_disable_redirects(self):
        class Response:
            status_code = 200
            text = ""

            def __init__(self, payload):
                self.payload = payload

            def json(self):
                return self.payload

        class Session:
            def __init__(self):
                self.calls = []
                self.responses = [
                    Response({"latest_version": {"id": "version"}}),
                    Response({"id": "prediction", "status": "starting"}),
                    Response({"id": "prediction", "status": "succeeded",
                              "output": ["https://cdn.example/result.png"]}),
                ]

            def get(self, url, **kwargs):
                self.calls.append(("GET", url, kwargs))
                return self.responses.pop(0)

            def post(self, url, **kwargs):
                self.calls.append(("POST", url, kwargs))
                return self.responses.pop(0)

        session = Session()
        client = replicate_images.ReplicateClient(
            api_key="bearer", session=session,
        )
        with mock.patch.object(
            network_policy.socket, "getaddrinfo", side_effect=_public_dns,
        ):
            result = client.run(
                "owner/model", {"prompt": "draw"},
                poll_interval=0, timeout=3,
            )
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual([method for method, _url, _kwargs in session.calls], [
            "GET", "POST", "GET",
        ])
        for _method, url, kwargs in session.calls:
            self.assertTrue(url.startswith("https://api.replicate.com/v1/"))
            self.assertIs(kwargs["allow_redirects"], False)
            self.assertEqual(kwargs["headers"]["Authorization"], "Token bearer")

    def test_replicate_redirect_is_terminal_and_url_safe(self):
        response = mock.Mock(status_code=302, text="")
        response.json.return_value = {
            "detail": "redirect https://evil.example/?token=secret",
        }
        session = mock.Mock()
        session.get.return_value = response
        client = replicate_images.ReplicateClient(
            api_key="bearer", session=session,
        )
        with mock.patch.object(
            network_policy.socket, "getaddrinfo", side_effect=_public_dns,
        ):
            with self.assertRaises(replicate_images.ReplicateError) as caught:
                client.poll("prediction")
        self.assertNotIn("secret", str(caught.exception))
        session.get.assert_called_once()
        self.assertIs(session.get.call_args.kwargs["allow_redirects"], False)


if __name__ == "__main__":
    unittest.main()
