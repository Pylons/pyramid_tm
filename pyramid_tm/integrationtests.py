"""Functional test suite to ensure transactions are correctly replayed.

See transaction replays and reifiers work correctly with PostgreSQL.
"""
import threading
import transaction

import pytest
import requests

from pyramid.config import Configurator
from webtest.http import StopableWSGIServer

from pyramid_tm import sample


@pytest.fixture
def settings():
    return {
        "sqlalchemy.url": "postgresql://localhost/pyramid_tm_functional"
    }


@pytest.fixture
def app(settings):
    config = Configurator(settings)
    config.scan(sample)
    return config.make_wsgi_app()


@pytest.fixture
def dbsession(request, config):
    """An SQLAlchemy session you can access from the unit test thread.

    Also resets database between subsequent test runs.
    """

    Base = sample.Base

    connection = engine.connect()

    with transaction.manager:
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)

    def teardown():
        with transaction.manager:
            Base.metadata.drop_all(engine)

        dbsession.close()

    request.addfinalizer(teardown)

    return dbsession


@pytest.fixture
def user(config):
    """Make sure database is initialized and we have one and only one User there."""
    return config.make_wsgi_app()


@pytest.fixture(scope="session")
def web_server(request, app, dbsession, users):
    port = 7788
    server = StopableWSGIServer.create(app, host="localhost", port=port)
    server.wait()

    def teardown():
        # Shutdown server thread
        server.shutdown()

    request.addfinalizer(teardown)
    host_base = "http://localhost:7788"
    return host_base


class SimulatenousRequestThread(threading.Thread):

    def __init__(self, func):
        super(SimulatenousRequestThread, self).__init__()
        self.func = func

    def run(self):
        self.result = self.func()


def test_replay(web_server):
    """Check simple conflict."""

    def hit_user():
        return requests.get(web_server + "/hit_user")

    t1 = SimulatenousRequestThread(hit_user)
    t2 = SimulatenousRequestThread(hit_user)
    t3 = SimulatenousRequestThread(hit_user)

    t1.start()
    t2.start()
    t3.start()

    t1.join()
    t2.join()
    t3.join()