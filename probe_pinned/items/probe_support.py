import importlib.util
import os
import sys


def solution():
    path = os.environ["SOLUTION_PATH"]
    spec = importlib.util.spec_from_file_location("solution_under_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
