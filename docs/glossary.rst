.. _glossary:

Glossary
========

.. glossary::
   :sorted:

   Pyramid
      A `web framework <https://docs.pylonsproject.org/projects/pyramid/en/latest/>`_.

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
      <https://pypi.org/project/transaction/>`__ used by ``pyramid_tm``.

   dotted Python name
     A reference to a Python object by name using a string, in the form
     ``path.to.modulename:attributename``.  Often used in Pyramid and
     Setuptools configurations.  A variant is used in dotted names within
     configurator method arguments that name objects (such as the "add_view"
     method's "view" and "context" attributes): the colon (``:``) is not
     used; in its place is a dot.
