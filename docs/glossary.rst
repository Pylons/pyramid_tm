.. _glossary:

Glossary
========

.. glossary::
   :sorted:

   Pyramid
      A `web framework <http://pylonshq.com/pyramid>`_.

   data manager
      The ``transaction`` package wraps data managers implemented for
      different transactional backends, such as SQLAlchemy
      (``zope.sqlalchemy``), but also many others.

   retryable
      A retryable exception is any exception that is recognized as retryable
      by an active :term:`data manager`. These errors usually inherit from
      ``transaction.interfaces.TransientError``. These errors are temporary
      and thus marked as retryable. For example, a serialization error in a
      database resulting from concurrent transactions.

   transaction
      A database transaction comprises a unit of work performed within a
      database management system.  In the context of the Pyramid documentation,
      "transaction" is also the name of a `Python package
      <http://pypi.python.org/pypi/transaction>`__ used by ``pyramid_tm``.
