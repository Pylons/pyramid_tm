"""Functional test suite to ensure transactions are correctly replayed.

See transaction replays and reifiers work correctly with PostgreSQL.
"""
import threading

import pytest
import requests

from pyramid.config import Configurator
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
    configurator.include("pyramid_tm")
    configurator.include(sample)
    return configurator.make_wsgi_app()


@pytest.fixture
def dbsession(request, registry):
    """An SQLAlchemy session you can access from the unit test thread.

    Also resets database between subsequent test runs.
    """

    Base = sample.Base

    engine = sample.create_engine(registry)

    # This is the transaction manager we use for the unit test
    # main thread
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
def web_server(request, app):
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


def test_resolvable(web_server, user, dbsession):
    """Check for a conflict the pyramid_tm can resolve.

    We are configured to two replay attempts.
    """

    sample.reset_test_counters()

    def hit_user():
        return requests.get(web_server + "/hit_user")

    # Do some concurrent database transactions
    t1 = SimulatenousRequestThread(hit_user)
    t2 = SimulatenousRequestThread(hit_user)

    t1.start()
    t2.start()

    t1.join()
    t2.join()

    # All request should have passed as 200
    for t in (t1, t2):
        assert t.result.status_code == 200

    # The view should be hit three times
    # 1. first transaction success
    # 2. second transaction conflict
    # 3. second transaction success
    assert sample.hit_views == 3

    with dbsession.tm:
        # The database counted correctly
        user = dbsession.query(sample.User).one()
        assert user.counter == 2


def test_unresolvable(web_server, user, dbsession):
    """Check for a conflict the pyramid_tm fails to resolve after retry attempt exceeed.
    We are configured to two replay attempts.
    """

    sample.reset_test_counters()

    def hit_user():
        return requests.get(web_server + "/hit_user")

    # Do some concurrent database transactions
    t1 = SimulatenousRequestThread(hit_user)
    t2 = SimulatenousRequestThread(hit_user)
    t3 = SimulatenousRequestThread(hit_user)

    t1.start()
    t2.start()
    t3.start()

    t1.join()
    t2.join()
    t3.join()

    threads = (t1, t2, t3)

    success_count = sum(1 for t in threads if t.result.status_code == 200)
    fail_count = sum(1 for t in threads if t.result.status_code == 500)

    # 2 out of 3 requests OK
    assert success_count == 2

    # This one could not be replayed
    assert fail_count == 1

    # The view should be hit three times
    # 1. first transaction success
    # 2. second transaction conflict
    # 3. second transaction success
    # 4. third transaction conflict
    # 5. third transaction conflict again
    assert sample.hit_views == 5

    # When the last transaction runs out of attempts in ends
    # up the exception view
    assert sample.exceptions_views == 1

    with dbsession.tm:
        # The database counted correctly
        user = dbsession.query(sample.User).one()
        assert user.counter == 2
