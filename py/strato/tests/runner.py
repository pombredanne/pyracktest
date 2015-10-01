import os
import unittest

if __name__ == "__main__":
    suite = unittest.TestLoader().discover(os.path.dirname(__file__), "test_*.py")
    unittest.TextTestRunner(verbosity=4).run(suite)
