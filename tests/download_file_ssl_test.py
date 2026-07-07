import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import Mock, patch


_MODULE_PATH = Path(__file__).resolve().parents[1] / "modules" / "utils" / "download_file.py"
_SPEC = spec_from_file_location("download_file_under_test", _MODULE_PATH)
download_file = module_from_spec(_SPEC)
_SPEC.loader.exec_module(download_file)


class DownloadFileSSLTests(unittest.TestCase):
    def test_https_downloads_use_certifi_ssl_context(self):
        response = Mock()
        response.close = Mock()
        context = object()

        with (
            patch.object(download_file, "_certifi_ssl_context", return_value=context),
            patch.object(download_file.urllib.request, "urlopen", return_value=response) as urlopen,
        ):
            with download_file._open_url("https://example.com/model.onnx"):
                pass

        self.assertIs(urlopen.call_args.kwargs["context"], context)


if __name__ == "__main__":
    unittest.main()
