from __future__ import with_statement

import sys
import transaction

from pyramid.util import DottedNameResolver
from pyramid.tweens import EXCVIEW
from pyramid_tm.compat import reraise

resolver = DottedNameResolver(None)

def default_commit_veto(request, response):
    """
    When used as a commit veto, the logic in this function will cause the
    transaction to be aborted if:

    - An ``X-Tm`` response header with the value ``abort`` (or any value
      other than ``commit``) exists.

    - The response status code starts with ``4`` or ``5``.

    Otherwise the transaction will be allowed to commit.
    """
    xtm = response.headers.get('x-tm')
    if xtm is not None:
        return xtm != 'commit'
    return response.status.startswith(('4', '5'))

class AbortResponse(Exception):
    def __init__(self, response):
        self.response = response

# work around broken "attempts" method of TransactionManager in transaction 
# 1.2.0
def _attempts(manager, number=3):
    assert number > 0
    while number:
        number -= 1
        if number:
            yield Attempt(manager)
        else:
            yield manager

class Attempt(object):

    def __init__(self, manager):
        self.manager = manager

    def _retry_or_raise(self, t, v, tb):
        retry = self.manager._retryable(t, v)
        self.manager.abort()
        if retry:
            return retry # suppress the exception if necessary
        reraise(t, v, tb) # otherwise reraise the exception
        
    def __enter__(self):
        return self.manager.__enter__()

    def __exit__(self, t, v, tb):

        if v is None:
            try:
                self.manager.commit()
            except:
                # this is what transaction 1.2.0 doesn't do (it doesn't
                # suppress retryable exceptions raised by a commit)
                return self._retry_or_raise(*sys.exc_info())
        else:
            return self._retry_or_raise(t, v, tb)
            
def tm_tween_factory(handler, registry, transaction=transaction):
    # transaction parameterized for testing purposes
    old_commit_veto = registry.settings.get('pyramid_tm.commit_veto', None)
    commit_veto = registry.settings.get('tm.commit_veto', old_commit_veto)
    attempts = int(registry.settings.get('tm.attempts', 1))
    commit_veto = resolver.maybe_resolve(commit_veto) if commit_veto else None

    def tm_tween(request):
        if 'repoze.tm.active' in request.environ:
            # don't handle txn mgmt if repoze.tm is in the WSGI pipeline
            return handler(request)

        try:
            for attempt in _attempts(transaction.manager, attempts):
                with attempt as t:
                    # make_body_seekable will copy wsgi.input if necessary,
                    # otherwise it will rewind the copy to position zero
                    if attempts != 1:
                        request.make_body_seekable()
                    response = handler(request)
                    if t.isDoomed():
                        raise AbortResponse(response)
                    if commit_veto is not None:
                        veto = commit_veto(request, response)
                        if veto:
                            raise AbortResponse(response)
                    return response
        except AbortResponse:
            e = sys.exc_info()[1] # py2.5-py3 compat
            return e.response

    return tm_tween

def includeme(config):
    """
    Set up am implicit 'tween' to do transaction management using the
    ``transaction`` package.  The tween will be slotted between the main
    Pyramid app and the Pyramid exception view handler.

    For every request it handles, the tween will begin a transaction by
    calling ``transaction.begin()``, and will then call the downstream
    handler (usually the main Pyramid application request handler) to obtain
    a response.  When attempting to call the downstream handler:

    - If an exception is raised by downstream handler while attempting to
      obtain a response, the transaction will be rolled back
      (``transaction.abort()`` will be called).

    - If no exception is raised by the downstream handler, but the
      transaction is doomed (``transaction.doom()`` has been called), the
      transaction will be rolled back.

    - If the deployment configuration specifies a ``tm.commit_veto`` setting,
      and the transaction management tween receives a response from the
      downstream handler, the commit veto hook will be called.  If it returns
      True, the transaction will be rolled back.  If it returns False, the
      transaction will be committed.

    - If none of the above conditions are True, the transaction will be
      committed (via ``transaction.commit()``).
    """
    config.add_tween('pyramid_tm.tm_tween_factory', under=EXCVIEW)
