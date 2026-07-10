import unittest

from waitcheck_proxy import build_wait_check_params


class WaitcheckProxyTests(unittest.TestCase):
    def test_stream_forwards_selected_date(self):
        self.assertEqual(
            build_wait_check_params("早班全体", "2026-07-09"),
            {"keyword": "早班全体", "date": "2026-07-09"},
        )

    def test_stream_omits_empty_date(self):
        self.assertEqual(
            build_wait_check_params("早班全体", ""),
            {"keyword": "早班全体"},
        )


if __name__ == "__main__":
    unittest.main()
