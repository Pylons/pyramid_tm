pyramid_tm
================

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

From now on, whenever a new request is setup, a new transaction is
associated with that request.

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
present in the ``repoze.tm2`` package as ``repoze.tm.default_commit_veto``
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
