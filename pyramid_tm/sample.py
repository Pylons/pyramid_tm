"""Functional test suite code."""
import random
import time
from pyramid.view import view_config
from sqlalchemy import (
    Column,
    Integer,
    String,
    )

from sqlalchemy.ext.declarative import declarative_base

from sqlalchemy.orm import (
    scoped_session,
    sessionmaker,
    )

from zope.sqlalchemy import ZopeTransactionExtension

DBSession = scoped_session(sessionmaker(extension=ZopeTransactionExtension()))

Base = declarative_base()

# How many time we hit different end points for a request
hit_views = 0
exceptions_views = 0


class User(Base):
    """Our poor user who is going be a very conflicted person."""

    __tablename__ = 'user'

    id = Column(Integer, primary_key=True)

    username = Column(String, unique=True)

    #: Used to see all requests go through
    counter = Column(Integer, default=0)


@view_config(route_name="hit_user")
def hit_user(request):
    """A view point hammering user, with random delays to simulate transaction conflict."""
    user = request.user
    user.counter += 1
    time.sleep(0.1 + random.random(0.5))

    global hit_views
    hit_views += 1


@view_config(route_name="exception_view")
def exception_view(request):
    """A view point hammering user, with random delays to simulate transaction conflict."""
    user = request.user
    user.counter += 1
    time.sleep(0.1 + random.random(0.5))

    global hit_views
    hit_views += 1


