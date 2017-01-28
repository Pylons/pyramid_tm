"""Transaction aware reify helpers."""
from pyramid.events import subscriber
from pyramid_tm import is_exc_retryable

from .events import TransactionAttempt


_marker = object()


def _subscribe_transaction_replay(config):
    config.add_subscriber(on_transaction_attempt_reset_reify, TransactionAttempt)
    config.add_request_method(can_access_transaction_in_excview, "can_access_transaction_in_excview")
    config.registry._transaction_aware_request_registered = True


def transaction_aware_reify(
        config,
        callable,
        name=None):
    """Make a request property reified in a transaction aware manner.

    Use this reifier for database aware request properties.

    IF there is a replay attempt due to a transaction conflict the result of the reified data is reset and looked up again on the next request play.

    Example:

    .. code-block:: python

        from pyramid_tm.reify import transaction_aware_reify

        def get_user(request):
            return request.dbsession.query(User).one_or_none()

        config.add_request_method(
            callable=transaction_aware_reify(config, get_user),
            name="user",
            property=True,
            reify=False)

    TODO: This could not be made a config directive, as having feature parity with add_request_method would force us to touch a lot of Pyramid internal APIs.

    :param config: Instance of :py:class:`pyramid.config.Configurator`

    :param callable: A function that takes ``request`` as a first arguments and plays around transaction aware stuff like databases

    :param name: (Optional) used internally to the reified stored value map
    """

    if name is None:
        name = callable.__name__

    def _reify(request):
        # Check if we have reified this result for this play

        if not hasattr(request, "_transaction_properties"):
            raise RuntimeError("There was an attempt to access transaction aware reified request property. However, for this request we never received transaction start event. This is usually a sign of incorrect tween stack order. Make sure pyramid_tm is the bottom-most tween before any tween accesses database. You can use ptweens command for this.")

        result = request._transaction_properties.get(name, _marker)
        if result is _marker:
            # Perform expensive transaction aware computation
            result = request._transaction_properties[name] = callable(request)
            #print("Updated ", request.path, request._transaction_properties, request.tm._txn)
            #print("Got ", request.path, request._transaction_properties)
        return result

    # Register our transaction event handler
    if getattr(config.registry, "_transaction_aware_request_registered", None) is None:
        _subscribe_transaction_replay(config)

    return _reify


@subscriber(TransactionAttempt)
def on_transaction_attempt_reset_reify(e):
    """Make sure we reset all reified properties if there is a replay."""
    reset_transaction_aware_properties(e.request)


def reset_transaction_aware_properties(request):
    """Reset all transaction aware properties on a request.

    You can call this e.g. when you need to abort the transaction manually in an internal server error view.
    """
    # This is the internal map where we are store reified results
    # over the request play
    #print("Resetting ", getattr(request, "_transaction_properties", None))
    request._transaction_properties = {}


def can_access_transaction_in_excview(exc, request):
    """Tell if it's ok to try to access database within the exception view.

    Because the exception view tween is executed the before th transaction tween, the transaction tween cannot enforce and delete reified transaction aware properties on a request in the case we have a conflict exception. Instead, the exception view must be careful and manually check the given exception before accessing any tranaction aware properties.

    This helper function is an API function to tell if it's safe to access reified methods or database in the exception view.

    It it safe to call this function only inside the exception view.

    :param request: HTTP request
    :param exc: Exception, the same as context paramter to the exception view
    :return: True if you can read e.g. request.user in the exception view
    """

    if exc is None:
        return False

    if is_exc_retryable(request, request.exc_info):
        # We got a transaction conflict exception ending up to the exception view.
        # It means we are out of transaction retry attemps.
        # It means database is having issues.
        # Don't try to access database in the exception view.
        return False

    return True