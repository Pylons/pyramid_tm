"""Functional test suite to ensure transactions are correctly replayed.

See transaction replays and reifiers work correctly with PostgreSQL.
"""
import threading
import transaction

import pytest
import requests

from pyramid.config import Configurator
from pyramid.registry import Registry
from sqlalchemy import engine_from_config
from transaction import TransactionManager
from webtest.http import StopableWSGIServer

from pyramid_tm import sample


@pytest.fixture
def settings():
    return sample.CONFIG


@pytest.fixture
def configurator(settings):
    return Configurator(settings=settings)


@pytest.fixture
def registry(configurator):
    return configurator.registry


@pytest.fixture
def app(configurator):
    configurator.include(sample)
    return configurator.make_wsgi_app()


@pytest.fixture
def dbsession(request, registry):
    """An SQLAlchemy session you can access from the unit test thread.

    Also resets database between subsequent test runs.
    """

    Base = sample.Base

    engine = sample.create_engine(registry)

    unit_test_tm = TransactionManager()
    dbsession = sample.create_session(registry, engine, unit_test_tm)

    with dbsession.tm:
        # Make sure we don't have leftover tables from the last run
        Base.metadata.drop_all(engine)
        # Recreate db
        Base.metadata.create_all(engine)

    def teardown():
        with dbsession.tm:
            Base.metadata.drop_all(engine)

        dbsession.close()

    request.addfinalizer(teardown)

    return dbsession


@pytest.fixture
def user(dbsession):
    """Create our test user."""
    with dbsession.tm:
        u = sample.User()
        dbsession.add(u)


@pytest.fixture
def web_server(request, app, dbsession):
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

    results = [t1.result, t2.result, t3.result]
    print(results)