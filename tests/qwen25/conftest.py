def pytest_configure(config):
    config.addinivalue_line("markers", "gpu: requires the formal GPU class")
    config.addinivalue_line("markers", "multinode: requires a two-node distributed runtime")
