pyramid_tm
==========

Overview
--------

``pyramid_tm`` is a package which allows :term:`Pyramid` requests to join
the active :term:`transaction` as provided by the :term:`transaction` package.

Installation
------------

Install using setuptools, e.g. (within a virtualenv)::

  $ easy_install pyramid_tm

Setup
-----

Once ``pyramid_tm`` is installed, you must use the ``config.include``
mechanism to include it into your Pyramid project's configuration.  In your
Pyramid project's ``__init__.py``:

.. code-block:: python
   :linenos:

   config = Configurator(.....)
   config.include('pyramid_tm')

From now on, whenever a new request is setup from an application using
``config``, a new transaction is associated with that request.

:term:`transaction` Usage
-------------------------

At the beginning of a request a new :term:`transaction` is started
using the ``transaction.begin()`` function.  Once the request has
finished all of it's works (ie views have finished running), a few checks
are tested:

  1) Did some other mechanism cause the transaction to become unstable? if so,
     ``transaction.abort()``.

  2) Did an exception occur in the underlying code? if so,
     ``transaction.abort()``

  3) Did the ``commit_veto`` callback result with True? if so,
     ``transaction.abort()``

If none of these checks called ``transaction.abort()`` then the
transaction is instead committed using ``transaction.commit()``.

By itself, this :term:`transaction` machinery doesn't do much.  It is
up to third-party code to *join* the active transaction to benefit.

See `repoze.filesafe <http://pypi.python.org/pypi/repoze.filesafe>`_
for an example of how files creation can be committed or rolled
back based on :term:`transaction`.


Using A Commit Veto
-------------------

If you'd like to veto commits based on the status code returned by the
downstream application, use a commit veto callback.

First, define the callback somewhere in your application:

.. code-block:: python
   :linenos:

   def commit_veto(environ, status, headers):
       for header_name, header_value in headers:
           if header_name.lower() == 'x-tm-abort':
               return True
       for bad in ('4', '5'):
           if status.startswith(bad):
               return True
       return False

Then configure it into your :term:`Configurator`.

Via Python:

.. code-block:: python
   :linenos:

   from pyramid.config import Configurator

   def app(global_conf, settings):
       settings['pyramid_tm.commit_veto'] = commit_veto
       config = Configurator(settings=settings)
       config.include('pyramid_tm')

Via PasteDeploy:

.. code-block:: ini
   :linenos:

   [app:myapp]
   pyramid_tm.commit_veto = my.package:commit_veto

In the PasteDeploy example, the path is a Python dotted name, where the dots
separate module and package names, and the colon separates a module from its
contents.  In the above example, the code would be implemented as a
"commit_veto" function which lives in the "package" submodule of the "my"
package.

The exact commit veto implementation shown above as an example is actually
present in the ``pyramid_tm`` package as ``pyramid_tm.default_commit_veto``
and used if no other commit_veto is specified.

More Information
----------------

.. toctree::
   :maxdepth: 1

   api.rst
   glossary.rst


Reporting Bugs / Development Versions
-------------------------------------

Visit http://github.com/Pylons/pyramid_tm to download development or
tagged versions.

Visit http://github.com/Pylons/pyramid_tm/issues to report bugs.

Indices and tables
------------------

* :ref:`glossary`
* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
