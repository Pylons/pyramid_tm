import sys
from pyramid.exceptions import ConfigurationError
from pyramid.settings import asbool
from pyramid.tweens import EXCVIEW
from pyramid.util import DottedNameResolver
import transaction
import warnings
import zope.interface

try:
    from pyramid_retry import IRetryableError
except ImportError:  # pragma: no cover
    IRetryableError = zope.interface.Interface

from .compat import reraise
from .compat import text_

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


class AbortWithResponse(Exception):
    """ Abort the transaction but return a pre-baked response."""
    def __init__(self, response):
        self.response = response


def tm_tween_factory(handler, registry):
    settings = registry.settings
    maybe_resolve = lambda val: resolver.maybe_resolve(val) if val else None
    old_commit_veto = settings.get('pyramid_tm.commit_veto', None)
    commit_veto = settings.get('tm.commit_veto', old_commit_veto)
    activate_hook = settings.get('tm.activate_hook')
    commit_veto = maybe_resolve(commit_veto)
    activate_hook = maybe_resolve(activate_hook)
    annotate_user = asbool(settings.get('tm.annotate_user', True))

    if 'tm.attempts' in settings:  # pragma: no cover
        warnings.warn('pyramid_tm removed support for the "tm.attempts" '
                      'setting in version 2.0. To re-enable retry support '
                      'enable pyramid_retry in your application.')

    def tm_tween(request):
        environ = request.environ
        if (
            # don't handle txn mgmt if repoze.tm is in the WSGI pipeline
            'repoze.tm.active' in environ or
            # pyramid_tm should only be active once
            'tm.active' in environ or
            # check activation hooks
            activate_hook is not None and not activate_hook(request)
        ):
            return handler(request)

        # grab a reference to the manager
        manager = request.tm

        # mark the environ as being managed by pyramid_tm
        environ['tm.active'] = True
        environ['tm.manager'] = manager

        try:
            t = manager.begin()

            # do not address the authentication policy until we are within
            # the transaction boundaries
            if annotate_user:
                userid = request.unauthenticated_userid
                if userid:
                    t.user = text_(userid)
            try:
                t.note(text_(request.path_info))
            except UnicodeDecodeError:
                t.note(text_("Unable to decode path as unicode"))

            response = handler(request)
            if manager.isDoomed():
                raise AbortWithResponse(response)

            # check for a squashed exception and handle it
            # this would happen if an exception view was invoked and
            # rendered an error response
            exc_info = getattr(request, 'exc_info', None)
            if exc_info is not None:
                maybe_tag_retryable(request, exc_info)
                raise AbortWithResponse(response)

            if commit_veto is not None:
                veto = commit_veto(request, response)
                if veto:
                    raise AbortWithResponse(response)
            manager.commit()
            return response

        except AbortWithResponse as e:
            manager.abort()
            return e.response

        except Exception:
            exc_info = sys.exc_info()
            try:
                maybe_tag_retryable(request, exc_info)
                reraise(*exc_info)

            finally:
                manager.abort()

                del exc_info # avoid leak

        # cleanup any changes we made to the request
        finally:
            del environ['tm.active']
            del environ['tm.manager']

    return tm_tween


def explicit_manager(request):
    """
    Create a new ``transaction.TransactionManager`` in explicit mode.

    This is recommended transaction manager and will help to weed out errors
    caused by code that tweaks the transaction before it has begun or after
    it has ended.

    """
    return transaction.TransactionManager(explicit=True)


def maybe_tag_retryable(request, exc_info):
    if request.tm._retryable(*exc_info[:-1]):
        exc = exc_info[1]
        if exc:
            zope.interface.alsoProvides(exc, IRetryableError)


def create_tm(request):
    manager_hook = request.registry.settings.get('tm.manager_hook')
    if manager_hook:
        manager_hook = resolver.maybe_resolve(manager_hook)
        return manager_hook(request)
    else:
        return transaction.manager


def is_tm_active(request):
    """
    Return ``True`` if the ``request`` is currently being managed by
    the pyramid_tm tween. If ``False`` then it may be necessary to manage
    transactions yourself.
    """
    return request.environ.get('tm.active', False)


class TMActivePredicate(object):
    """
    A :term:`view predicate` registered as ``tm_active``. Can be used
    to determine if an exception view should execute based on whether it's
    the last retry attempt before aborting the request.

    .. seealso:: See :func:`pyramid_tm.is_tm_active`.

    """
    def __init__(self, val, config):
        if not isinstance(val, bool):
            raise ConfigurationError(
                'The "tm_active" view predicate value must be '
                'True or False.',
            )
        self.val = val

    def text(self):
        return 'tm_active = %s' % (self.val,)

    phash = text

    def __call__(self, context, request):
        is_active = is_tm_active(request)
        return ((self.val and is_active) or (not self.val and not is_active))


def includeme(config):
    """
    Set up an implicit 'tween' to do transaction management using the
    ``transaction`` package.  The tween will be slotted between the Pyramid
    request ingress and the Pyramid exception view handler.

    For every request it handles, the tween will begin a transaction by
    calling ``request.tm.begin()``, and will then call the downstream
    handler (usually the main Pyramid application request handler) to obtain
    a response.  When attempting to call the downstream handler:

    - If an exception is raised by downstream handler while attempting to
      obtain a response, the transaction will be rolled back
      (``request.tm.abort()`` will be called).

    - If no exception is raised by the downstream handler, but the
      transaction is doomed (``request.tm.doom()`` has been called), the
      transaction will be rolled back.

    - If the deployment configuration specifies a ``tm.commit_veto`` setting,
      and the transaction management tween receives a response from the
      downstream handler, the commit veto hook will be called.  If it returns
      True, the transaction will be rolled back.  If it returns ``False``, the
      transaction will be committed.

    - If none of the above conditions are true, the transaction will be
      committed (via ``request.tm.commit()``).

    """
    config.add_tween('pyramid_tm.tm_tween_factory', over=EXCVIEW)
    config.add_request_method(create_tm, name='tm', reify=True)
    config.add_view_predicate('tm_active', TMActivePredicate)

    def ensure():
        manager_hook = config.registry.settings.get("tm.manager_hook")
        if manager_hook is not None:
            manager_hook = resolver.maybe_resolve(manager_hook)
            config.registry.settings["tm.manager_hook"] = manager_hook

    config.action(None, ensure, order=10)
