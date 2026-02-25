import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "write_greet_fn"))

from greet import greet

for name in ["Alice", "Bob", "Carol"]:
    print(greet(name))
