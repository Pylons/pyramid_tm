# -*- coding: utf-8 -*-
"""Integration example code."""

import random
import time

from pyramid.httpexceptions import HTTPOk, HTTPInternalServerError
from pyramid.view import view_config
from sqlalchemy import (
    Column,
    Integer,
    String,
    )
from sqlalchemy import engine_from_config

from sqlalchemy.ext.declarative import declarative_base

from sqlalchemy.orm import (
    sessionmaker,
    )

import zope.sqlalchemy

from pyramid_tm.reify import transaction_aware_reify


CONFIG = {
    "sqlalchemy.url": "postgresql://localhost/pyramid_tm_integration",

    # We can handle up to 2 conflicting transactions before one request falls flat
    "tm.attempts": 2,
}


Base = declarative_base()

# How many time we hit different end points for a request
hit_views = 0
exceptions_views = 0


class User(Base):
    """Our poor user who is going be a very conflicted person."""

    __tablename__ = 'user'

    id = Column(Integer, primary_key=True)

    #: We use this column to cause transaction conflicts by incrementing the
    #: column in different transactions at the same time
    counter = Column(Integer, default=0)


def create_engine(registry):
    engine = engine_from_config(registry.settings, 'sqlalchemy.', client_encoding='utf8', isolation_level='SERIALIZABLE')
    return engine


def create_session(registry, engine, transaction_manager):
    """Create a new database session from a process specific connection pool.

    We do not use thread-local transaaction.manager, but expose the transaction manager as dbsession.tm attribute.
    """

    # Make sure we create session maker only once per process,
    # as otherwise SQLAlchemy connection pooling doesn't work.
    # We assume the lifecycle of the registry matches the life cycle
    # of SQLAlchemy process pool.
    db_session_maker = getattr(registry, "db_session_maker", None)

    if not db_session_maker:
        engine = create_engine(registry)

        dbmaker = sessionmaker()
        dbmaker.configure(bind=engine)

        db_session_maker = registry.db_session_maker = dbmaker

    # Pull out a new session from a connection pool
    dbsession = db_session_maker()
    zope.sqlalchemy.register(dbsession, transaction_manager=transaction_manager)

    # Expose transaction manager with the dbsession
    dbsession.tm = transaction_manager

    return dbsession


@view_config(route_name="hit_user")
def hit_user(request):
    """A view point hammering user, with random delays to simulate transaction conflict."""
    user = request.user
    user.counter += 1
    time.sleep(0.1 + random.random())

    global hit_views
    hit_views += 1
    return HTTPOk("OK")


@view_config(context=Exception)
def exception_view(request):
    """This is were we end up if the transaction conflict cannot be resolved."""
    global exceptions_views
    exceptions_views += 1
    return HTTPInternalServerError("Ei mennyt niin kuin strömsöössä")


def includeme(config):
    """Set up the sample application."""
    from pyramid_tm import sample

    def dbsession(request):
        engine = create_engine(request.registry)
        return create_session(request.registry, engine, request.tm)

    def get_user(request):
        # Assume our database has 0..1 users
        return request.dbsession.query(User).one_or_none()

    config.add_route("hit_user", "/hit_user")
    config.add_route("exception_view", "/exception_view")
    config.add_request_method(dbsession, "dbsession", reify=True)
    config.add_request_method(
        callable=transaction_aware_reify(config, get_user),
        name="user",
        property=True,
        reify=False)

    config.scan(sample)


def reset_test_counters():
    global hit_views
    global exceptions_views
    hit_views = 0
    exceptions_views = 0