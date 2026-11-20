import pytest

from tests.fixtures import build_all


@pytest.fixture(scope="session")
def clips(tmp_path_factory):
    return build_all(tmp_path_factory.mktemp("clips"))
