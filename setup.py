##############################################################################
#
# Copyright (c) 2008-2011 Agendaless Consulting and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the BSD-like license at
# http://www.repoze.org/LICENSE.txt.  A copy of the license should accompany
# this distribution.  THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL
# EXPRESS OR IMPLIED WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO,
# THE IMPLIED WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND
# FITNESS FOR A PARTICULAR PURPOSE
#
##############################################################################

import os

from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))
try:
    README = open(os.path.join(here, 'README.rst')).read()
    CHANGES = open(os.path.join(here, 'CHANGES.rst')).read()
except IOError:
    README = CHANGES = ''

install_requires = [
    'pyramid>=1.2dev',
    'transaction',
    ]

tests_require = [
    'WebTest',
]

testing_extras = tests_require + ['nose', 'coverage']
docs_extras = [
    'Sphinx',
    'pylons-sphinx-themes',
]

setup(name='pyramid_tm',
      version='1.0.1',
      description=('A package which allows Pyramid requests to join the '
                   'active transaction'),
      long_description=README + '\n\n' + CHANGES,
      classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.4",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: Implementation :: CPython",
        "Programming Language :: Python :: Implementation :: PyPy",
        "Framework :: Pyramid",
        "Topic :: Internet :: WWW/HTTP :: WSGI",
        "License :: Repoze Public License",
        ],
      keywords='wsgi pylons pyramid transaction',
      author="Rocky Burt, Chris McDonough",
      author_email="pylons-devel@googlegroups.com",
      url="http://docs.pylonsproject.org/projects/pyramid-tm/en/latest/",
      license="BSD-derived (http://www.repoze.org/LICENSE.txt)",
      packages=find_packages(),
      include_package_data=True,
      zip_safe=False,
      install_requires=install_requires,
      tests_require=tests_require,
      test_suite="pyramid_tm",
      entry_points='',
      extras_require = {
          'testing':testing_extras,
          'docs':docs_extras,
          },
      )
