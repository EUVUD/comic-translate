import unittest
from unittest import mock

from modules.utils import download_file


class DownloadFileSslTests(unittest.TestCase):
    def test_open_url_passes_ssl_context_for_https(self):
        sentinel_context = object()
        fake_response = mock.Mock()

        with mock.patch.object(
            download_file, "_certifi_ssl_context", return_value=sentinel_context
        ), mock.patch.object(
            download_file.urllib.request, "urlopen", return_value=fake_response
        ) as urlopen:
            with download_file._open_url("https://example.com/model.onnx"):
                pass

        self.assertEqual(urlopen.call_args.kwargs["context"], sentinel_context)
        fake_response.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
