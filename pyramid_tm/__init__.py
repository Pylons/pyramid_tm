import sys
import transaction

from pyramid.httpexceptions import HTTPNotFound
from pyramid.interfaces import IRequestExtensions
from pyramid.interfaces import IRequestFactory
from pyramid.request import Request, apply_request_extensions
from pyramid.settings import asbool
from pyramid.threadlocal import manager as request_manager
from pyramid.tweens import EXCVIEW
from pyramid.util import DottedNameResolver

from pyramid_tm.compat import reraise
from pyramid_tm.compat import native_

from pyramid_tm.events import TransactionAttempt


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
    old_commit_veto = settings.get('pyramid_tm.commit_veto', None)
    commit_veto = settings.get('tm.commit_veto', old_commit_veto)
    activate = settings.get('tm.activate_hook')
    attempts = int(settings.get('tm.attempts', 1))
    commit_veto = resolver.maybe_resolve(commit_veto) if commit_veto else None
    activate = resolver.maybe_resolve(activate) if activate else None
    annotate_user = asbool(settings.get('tm.annotate_user', True))
    request_factory = registry.queryUtility(IRequestFactory, default=Request)
    request_extensions = registry.queryUtility(IRequestExtensions)
    assert attempts > 0

    def tm_tween(request):
        if (
            # don't handle txn mgmt if repoze.tm is in the WSGI pipeline
            'repoze.tm.active' in request.environ or
            # pyramid_tm should only be active once
            'tm.active' in request.environ or
            # check activation hooks
            activate is not None and not activate(request)
        ):
            return handler(request)

        # if we are supporting multiple attempts then we must make
        # make the body seekable in order to re-use it across multiple
        # attempts. make_body_seekable will copy wsgi.input if
        # necessary, otherwise it will rewind the copy to position zero
        if attempts != 1:
            request.make_body_seekable()

        # hang onto a reference to the original request as it's the thing
        # used above the tm tween, we can't change that
        orig_request = request
        manager = None

        for number in range(attempts):
            is_last_attempt = (number == attempts - 1)

            # track the attempt info in the environ
            # try to set it as soon as possible so that it's available
            # in the request factory and elsewhere if people want it
            # note: set all of these values here as they are cleared after
            # each attempt
            environ = request.environ
            environ['tm.active'] = True
            environ['tm.attempt'] = number
            environ['tm.attempts'] = attempts

            # do not touch request.tm until we've set it active or it'll raise
            if manager is None:
                manager = request.tm

            # if we are not on the first attempt then we should start
            # with a new request object and throw away any changes to
            # the old object, however we do this carefully to try and
            # avoid extra copies of the body
            if number > 0:
                # try to make sure this code stays in sync with pyramid's
                # router which normally creates requests
                request = request_factory(environ)
                request.tm = manager
                request.registry = registry
                request.invoke_subrequest = orig_request.invoke_subrequest
                apply_request_extensions(request, extensions=request_extensions)

            # push the new request onto the threadlocal stack
            # this should be safe unless someone is doing something
            # really funky
            request_manager.push({
                'request': request,
                'registry': registry,
            })

            try:
                t = manager.begin()

                # do not address the authentication policy until we are within
                # the transaction boundaries
                if annotate_user:
                    userid = request.unauthenticated_userid
                    if userid:
                        userid = native_(userid, 'utf-8')
                        t.setUser(userid, '')
                try:
                    t.note(native_(request.path_info, 'utf-8'))
                except UnicodeDecodeError:
                    t.note("Unable to decode path as unicode")

                e = TransactionAttempt(request, t, number)
                registry.notify(e)

                response = handler(request)
                if manager.isDoomed():
                    raise AbortWithResponse(response)

                # check for a squashed exception and handle it
                # this would happen if an exception view was invoked and
                # rendered an error response
                exc_info = getattr(request, 'exc_info', None)
                if exc_info is not None:
                    # if this was the last attempt or the exception is not
                    # retryable use this response instead of raising and
                    # having a new error response generated
                    if (
                        is_last_attempt or
                        not is_exc_retryable(request, exc_info)
                    ):
                        raise AbortWithResponse(response)

                    # the exception is retryable so we'll squash the response
                    # and loop around to try again
                    else:
                        reraise(*exc_info)

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
                    # if this was the last attempt or the exception is not
                    # retryable then make a last ditch effort to render an
                    # error response before sending the exception up the stack
                    if (
                        is_last_attempt or
                        not is_exc_retryable(request, exc_info)
                    ):
                        return render_exception(request, exc_info)

                finally:
                    # keep the manager alive until after invoke_exception_view
                    manager.abort()

                    del exc_info # avoid leak

            # cleanup any changes we made to the request
            finally:
                request_manager.pop()

                del environ['tm.active']
                del environ['tm.attempt']
                del environ['tm.attempts']

                # propagate exception info back to the original request,
                # possibly clearing out a retryable error triggered from the
                # first attempt
                orig_request.exception = getattr(request, 'exception', None)
                orig_request.exc_info = getattr(request, 'exc_info', None)

    return tm_tween


def render_exception(request, exc_info):
    try:
        return request.invoke_exception_view(exc_info)
    except HTTPNotFound:
        reraise(*exc_info)


def is_exc_retryable(request, exc_info):
    """
    Return ``True`` if the exception is recognized as :term:`retryable`.

    This will return ``False`` if ``pyramid_tm`` is inactive for the request.

    """
    if not request.environ.get('tm.active', False):
        return False
    if exc_info is None:
        return False
    return request.tm._retryable(*exc_info[:-1])


def is_last_attempt(request):
    """
    Return ``True`` if the ``request`` is being executed as the last
    attempt, meaning that ``pyramid_tm`` will not be issuing any new attempts,
    regardless of what happens when executing this request.

    This will return ``True`` if ``pyramid_tm`` is inactive for the request.

    """
    environ = request.environ
    if not environ.get('tm.active', False):
        return True

    return environ['tm.attempt'] == environ['tm.attempts'] - 1


class RetryableExceptionPredicate(object):
    """
    A :term:`view predicate` registered as ``tm_exc_is_retryable``. Can be
    used to determine if an exception view should execute based on whether
    the exception is :term:`retryable`.

    """
    def __init__(self, val, config):
        self.val = val

    def text(self):
        return 'tm_exc_is_retryable = %s' % (self.val,)

    phash = text

    def __call__(self, context, request):
        exc_info = getattr(request, 'exc_info', None)
        is_retryable = is_exc_retryable(request, exc_info)
        return (
            (self.val and is_retryable)
            or (not self.val and not is_retryable)
        )


class LastAttemptPredicate(object):
    """
    A :term:`view predicate` registered as ``tm_last_attempt``. Can be used
    to determine if an exception view should execute based on whether it's
    the last attempt by ``pyramid_tm``.

    """
    def __init__(self, val, config):
        self.val = val

    def text(self):
        return 'tm_last_attempt = %s' % (self.val,)

    phash = text

    def __call__(self, context, request):
        is_last = is_last_attempt(request)
        return ((self.val and is_last) or (not self.val and not is_last))


def create_tm(request):
    if 'tm.active' not in request.environ:
        raise AttributeError('tm inactive for request or accessed above tm '
                             'tween')
    manager_hook = request.registry.settings.get('tm.manager_hook')
    if manager_hook:
        manager_hook = resolver.maybe_resolve(manager_hook)
        return manager_hook(request)
    else:
        return transaction.manager


def includeme(config):
    """
    Set up an implicit 'tween' to do transaction management using the
    ``transaction`` package.  The tween will be slotted between the Pyramid
    request ingress and the Pyramid exception view handler.

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
      True, the transaction will be rolled back.  If it returns ``False``, the
      transaction will be committed.

    - If none of the above conditions are true, the transaction will be
      committed (via ``transaction.commit()``).

    This function also sets up two :term:`view predicates <view predicate>`,
    ``tm_last_attempt=True/False`` and ``tm_exc_is_retryable=True/False``
    which can be used by views and exception views to determine whether they
    should execute.

    """
    config.add_request_method(create_tm, name='tm', reify=True)
    config.add_tween('pyramid_tm.tm_tween_factory', over=EXCVIEW)
    config.add_view_predicate('tm_last_attempt', LastAttemptPredicate)
    config.add_view_predicate(
        'tm_exc_is_retryable', RetryableExceptionPredicate)

    def ensure():
        manager_hook = config.registry.settings.get("tm.manager_hook")
        if manager_hook is not None:
            manager_hook = resolver.maybe_resolve(manager_hook)
            config.registry.settings["tm.manager_hook"] = manager_hook

    config.action(None, ensure, order=10)
    config.add_directive("add_transaction_aware_request_method", "pyramid_tm.reify.add_transaction_aware_request_method")