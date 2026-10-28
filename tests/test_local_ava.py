"""Offline tests for the experimental on-device AVA adapter."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock

FILE = Path(__file__).resolve().parents[1] / "custom_components" / "dreame_vacuum" / "dreame" / "local_ava.py"
spec = importlib.util.spec_from_file_location("local_ava", FILE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
LocalAva = module.DreameVacuumLocalAvaProtocol


def response(payload=None, status=200, content=b"map bytes"):
    result = Mock()
    result.status_code = status
    result.json.return_value = payload
    result.content = content
    return result


class TestLocalAva(unittest.TestCase):
    def setUp(self):
        self.client = LocalAva("http://127.0.0.1:8080", "my-secret")
        self.client._session.request = Mock(side_effect=[
            response({"model": "dreame.vacuum.r2505",
                      "mac": "AA:BB:CC:DD:EE:FF", "did": "123",
                      "fw_ver": "4.3.0_1234"}),
            response({"id": 10, "result": [
                {"siid": 4, "piid": 19, "value": "matched", "code": 0}
            ]}),
        ])

    def test_connect_and_properties(self):
        info = self.client.connect()
        self.assertEqual(info["model"], "dreame.vacuum.r2505")
        self.assertEqual(self.client.device_id, "123")
        props = self.client.send("get_properties",
                                 [{"did": "42", "siid": 4, "piid": 19}])
        self.assertEqual(props[0]["did"], "42")
        self.assertEqual(props[0]["value"], "matched")
        args, kwargs = self.client._session.request.call_args
        self.assertEqual(args, ("POST", "http://127.0.0.1:8080/api/rpc"))
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer my-secret")
        self.assertFalse(kwargs["allow_redirects"])

    def test_external_map_url_rejected(self):
        self.assertIsNone(self.client.get_file("https://third-party.invalid/api/maps"))
        self.client._session.request.assert_not_called()

    def test_no_arbitrary_endpoint(self):
        for host in ("https://user:pass@127.0.0.1", "http://127.0.0.1:80/other",
                     "file:///etc/passwd"):
            with self.assertRaises(ValueError):
                LocalAva(host)

    def test_unauthorized_agent(self):
        self.client._session.request = Mock(return_value=response(status=401))
        self.assertFalse(self.client.login())
        self.assertTrue(self.client.auth_failed)


if __name__ == "__main__":
    unittest.main()
