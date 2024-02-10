''' Tests for runpod.serverless.modules.rp_fastapi.py '''
# pylint: disable=protected-access

import os
import asyncio

import aiohttp
import unittest
from unittest.mock import patch, Mock, MagicMock
import pytest

import runpod
from runpod.serverless.modules import rp_fastapi


class TestFastAPI(unittest.TestCase):
    ''' Tests the FastAPI '''

    def setUp(self) -> None:
        self.handler = Mock()
        self.handler.return_value = {"result": "success"}

        self.error_handler = Mock()
        self.error_handler.side_effect = Exception("test error")

    def test_start_serverless_with_realtime(self):
        '''
        Tests the start_serverless() method with the realtime option.
        '''
        module_location = "runpod.serverless.modules.rp_fastapi"
        with patch(f"{module_location}.Heartbeat.start_ping", Mock()) as mock_ping, \
                patch(f"{module_location}.FastAPI", Mock()) as mock_fastapi, \
                patch(f"{module_location}.APIRouter", return_value=Mock()) as mock_router, \
                patch(f"{module_location}.uvicorn", Mock()) as mock_uvicorn:

            rp_fastapi.RUNPOD_REALTIME_PORT = '1111'
            rp_fastapi.RUNPOD_ENDPOINT_ID = 'test_endpoint_id'

            os.environ["RUNPOD_REALTIME_PORT"] = '1111'
            os.environ["RUNPOD_ENDPOINT_ID"] = 'test_endpoint_id'

            runpod.serverless.start({"handler": self.handler})

            self.assertTrue(mock_ping.called)

            self.assertTrue(mock_fastapi.called)
            self.assertTrue(mock_router.called)

            self.assertTrue(rp_fastapi.RUNPOD_ENDPOINT_ID == 'test_endpoint_id')
            self.assertTrue(mock_router.return_value.add_api_route.called)

            self.assertTrue(mock_uvicorn.run.called)

            os.environ.pop("RUNPOD_REALTIME_PORT")
            os.environ.pop("RUNPOD_ENDPOINT_ID")

    @pytest.mark.asyncio
    def test_webhook_sender(self):
        '''
        Tests the _webhook_sender() method.
        '''
        loop = asyncio.get_event_loop()

        module_location = "runpod.serverless.modules.rp_fastapi.aiohttp.ClientSession"

        with patch(f"{module_location}.post", new_callable=MagicMock) as mock_post:
            mock_post.return_value.__aenter__.return_value = MagicMock(
                status=200)  # Simulate success response
            mock_post.return_value.__aexit__.return_value = None

            success = asyncio.run(rp_fastapi._send_webhook_async(
                "test_webhook", {"test": "output"}))
            assert success is True

            mock_post.return_value.__aenter__.return_value.raise_for_status.side_effect = aiohttp.ClientResponseError(  # pylint: disable=line-too-long
                request_info=None, history=None, status=500)

            success = asyncio.run(rp_fastapi._send_webhook_async(
                "test_webhook", {"test": "output"}))
            assert success is False

        loop.close()

    @pytest.mark.asyncio
    def test_run(self):
        '''
        Tests the _run() method.
        '''
        loop = asyncio.get_event_loop()

        module_location = "runpod.serverless.modules.rp_fastapi"
        with patch(f"{module_location}.Heartbeat.start_ping", Mock()) as mock_ping, \
                patch(f"{module_location}.FastAPI", Mock()), \
                patch(f"{module_location}.APIRouter", return_value=Mock()), \
                patch(f"{module_location}.uvicorn", Mock()), \
                patch(f"{module_location}.uuid.uuid4", return_value="123"):

            job_object = rp_fastapi.Job(
                id="test_job_id",
                input={"test_input": "test_input"}
            )

            default_input_object = rp_fastapi.DefaultRequest(
                input={"test_input": "test_input"}
            )

            # Test with handler
            worker_api = rp_fastapi.WorkerAPI({"handler": self.handler})

            run_return = asyncio.run(worker_api._realtime(job_object))
            assert run_return == {"output": {"result": "success"}}

            debug_run_return = asyncio.run(worker_api._sim_run(default_input_object))
            assert debug_run_return == {
                "id": "test-123",
                "status": "IN_PROGRESS"
            }

            self.assertTrue(mock_ping.called)

            # Test with generator handler
            def generator_handler(job):
                del job
                yield {"result": "success"}

            generator_worker_api = rp_fastapi.WorkerAPI({"handler": generator_handler})
            generator_run_return = asyncio.run(generator_worker_api._sim_run(default_input_object))
            assert generator_run_return == {
                "id": "test-123",
                "status": "IN_PROGRESS"
            }

        loop.close()

    @pytest.mark.asyncio
    def test_runsync(self):
        '''
        Tests the _runsync() method.
        '''
        loop = asyncio.get_event_loop()

        module_location = "runpod.serverless.modules.rp_fastapi"
        with patch(f"{module_location}.FastAPI", Mock()), \
                patch(f"{module_location}.APIRouter", return_value=Mock()), \
                patch(f"{module_location}.uvicorn", Mock()), \
                patch(f"{module_location}.uuid.uuid4", return_value="123"):

            default_input_object = rp_fastapi.DefaultRequest(
                input={"test_input": "test_input"}
            )

            input_object_with_webhook = rp_fastapi.DefaultRequest(
                input={"test_input": "test_input"},
                webhook="test_webhook"
            )

            # Test with handler
            worker_api = rp_fastapi.WorkerAPI({"handler": self.handler})

            runsync_return = asyncio.run(worker_api._sim_runsync(default_input_object))
            assert runsync_return == {
                "id": "test-123",
                "status": "COMPLETED",
                "output": {"result": "success"}
            }

            # Test with generator handler
            def generator_handler(job):
                del job
                yield {"result": "success"}

            generator_worker_api = rp_fastapi.WorkerAPI({"handler": generator_handler})
            generator_runsync_return = asyncio.run(
                generator_worker_api._sim_runsync(default_input_object))
            assert generator_runsync_return == {
                "id": "test-123",
                "status": "COMPLETED",
                "output": [{"result": "success"}]
            }

            # Test with error handler
            error_worker_api = rp_fastapi.WorkerAPI({"handler": self.error_handler})
            error_runsync_return = asyncio.run(
                error_worker_api._sim_runsync(default_input_object))
            assert "error" in error_runsync_return

            # Test webhook caller sent
            with patch(f"{module_location}._send_webhook_async", return_value=True) as mock_send_webhook:  # pylint: disable=line-too-long
                asyncio.run(worker_api._sim_runsync(input_object_with_webhook))
                assert mock_send_webhook.called

        loop.close()

    @pytest.mark.asyncio
    def test_stream(self):
        '''
        Tests the _stream() method.
        '''
        loop = asyncio.get_event_loop()

        module_location = "runpod.serverless.modules.rp_fastapi"
        with patch(f"{module_location}.FastAPI", Mock()), \
                patch(f"{module_location}.APIRouter", return_value=Mock()), \
                patch(f"{module_location}.uvicorn", Mock()), \
                patch(f"{module_location}.uuid.uuid4", return_value="123"):

            default_input_object = rp_fastapi.DefaultRequest(
                input={"test_input": "test_input"}
            )

            input_object_with_webhook = rp_fastapi.DefaultRequest(
                input={"test_input": "test_input"},
                webhook="test_webhook"
            )

            worker_api = rp_fastapi.WorkerAPI({"handler": self.handler})

            # Add job to job_list
            asyncio.run(worker_api._sim_run(default_input_object))

            stream_return = asyncio.run(worker_api._sim_stream("test_job_id"))
            assert stream_return == {
                "id": "test_job_id",
                "status": "FAILED",
                "error": "Job ID not found"
            }

            stream_return = asyncio.run(worker_api._sim_stream("test-123"))
            assert stream_return == {
                "id": "test-123",
                "status": "FAILED",
                "error": "Stream not supported, handler must be a generator."
            }

            # Test with generator handler
            def generator_handler(job):
                del job
                yield {"result": "success"}

            generator_worker_api = rp_fastapi.WorkerAPI({"handler": generator_handler})
            generator_stream_return = asyncio.run(
                generator_worker_api._sim_stream("test-123"))
            assert generator_stream_return == {
                "id": "test-123",
                "status": "COMPLETED",
                "stream": [{"output": {"result": "success"}}]
            }

            # Test webhook caller sent
            with patch(f"{module_location}._send_webhook_async", return_value=True) as mock_send_webhook:  # pylint: disable=line-too-long
                asyncio.run(worker_api._sim_stream(input_object_with_webhook))
                assert mock_send_webhook.called

        loop.close()

    @pytest.mark.asyncio
    def test_status(self):
        '''
        Tests the _status() method.
        '''
        loop = asyncio.get_event_loop()

        module_location = "runpod.serverless.modules.rp_fastapi"
        with patch(f"{module_location}.FastAPI", Mock()), \
                patch(f"{module_location}.APIRouter", return_value=Mock()), \
                patch(f"{module_location}.uvicorn", Mock()), \
                patch(f"{module_location}.uuid.uuid4", return_value="123"):

            worker_api = rp_fastapi.WorkerAPI({"handler": self.handler})

            default_input_object = rp_fastapi.DefaultRequest(
                input={"test_input": "test_input"}
            )

            # Add job to job_list
            asyncio.run(worker_api._sim_run(default_input_object))

            status_return = asyncio.run(worker_api._sim_status("test_job_id"))
            assert status_return == {
                "id": "test_job_id",
                "status": "FAILED",
                "error": "Job ID not found"
            }

            status_return = asyncio.run(worker_api._sim_status("test-123"))
            assert status_return == {
                "id": "test-123",
                "status": "COMPLETED",
                "output": {"result": "success"}
            }

            # Test with generator handler
            def generator_handler(job):
                del job
                yield {"result": "success"}
            generator_worker_api = rp_fastapi.WorkerAPI({"handler": generator_handler})
            asyncio.run(generator_worker_api._sim_run(default_input_object))
            generator_stream_return = asyncio.run(
                generator_worker_api._sim_status("test-123"))
            assert generator_stream_return == {
                "id": "test-123",
                "status": "COMPLETED",
                "output": [{"result": "success"}]
            }

            # Test with error handler
            error_worker_api = rp_fastapi.WorkerAPI({"handler": self.error_handler})
            asyncio.run(error_worker_api._sim_run(default_input_object))
            error_status_return = asyncio.run(
                error_worker_api._sim_status("test-123"))
            assert "error" in error_status_return

        loop.close()
