from pyramid.util import DottedNameResolver
from pyramid.tweens import EXCVIEW

import transaction

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
        if xtm == 'commit':
            return False
        return True
    status = response.status
    for bad in ('4', '5'):
        if status.startswith(bad):
            return True
    return False

def tm_tween_factory(handler, registry, transaction=transaction):
    # transaction parameterized for testing purposes
    commit_veto = registry.settings.get('pyramid_tm.commit_veto')
    if commit_veto is not None:
        commit_veto = resolver.resolve(commit_veto)

    def tm_tween(request):
        if 'repoze.tm.active' in request.environ:
            return handler(request)

        t = transaction.get()
        t.begin()

        try:
            response = handler(request)
        except:
            t.abort()
            raise

        if transaction.isDoomed():
            t.abort()
        elif commit_veto is not None:
            veto = commit_veto(request, response)
            if veto:
                t.abort()
            else:
                t.commit()
        else:
            t.commit()

        return response
        
    return tm_tween

def includeme(config):
    """
    Set up a 'tween' to do transaction management using the ``transaction``
    package.  The tween will be slotted between the main Pyramid app and the
    Pyramid exception view handler.

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

    - If the deployment configuration specifies a ``pyramid_tm.commit_veto``
      setting, and the transaction management tween receives a response from
      the downstream handler, the commit veto hook will be called.  If it
      returns True, the transaction will be rolled back.  If it returns
      False, the transaction will be committed.

    - If none of the above conditions are True, the transaction will be
      committed (via ``transaction.commit()``).
    """
    config.add_tween(tm_tween_factory, above=EXCVIEW)
