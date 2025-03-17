# mock_input.py
# Save this as a new file in your project directory

import builtins

class MockInput:
    def __init__(self, return_value='y'):
        self.return_value = return_value
        self.original_input = builtins.input

    def mock_input(self, prompt=''):
        print(f"[AUTO RESPONSE] Input prompt '{prompt}' automatically answered with '{self.return_value}'")
        return self.return_value

    def __enter__(self):
        builtins.input = self.mock_input
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        builtins.input = self.original_input