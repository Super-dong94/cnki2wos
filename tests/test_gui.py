import unittest

from cnki2wos.gui import ConverterApp, main


class GuiImportTests(unittest.TestCase):
    def test_gui_entry_points_are_callable(self):
        self.assertTrue(callable(ConverterApp))
        self.assertTrue(callable(main))


if __name__ == "__main__":
    unittest.main()
