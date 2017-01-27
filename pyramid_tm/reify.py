"""Transaction aware reify helpers."""
from pyramid.events import subscriber

from .events import TransactionAttempt


_marker = object()


def _subscribe_transaction_replay(config):
    config.add_subscriber(on_transaction_attempt_reset_reify, TransactionAttempt)
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
        return result

    # Register our transaction event handler
    if getattr(config.registry, "_transaction_aware_request_registered", None) is None:
        _subscribe_transaction_replay(config)

    return _reify


@subscriber(TransactionAttempt)
def on_transaction_attempt_reset_reify(e):
    # This is the internal map where we are store reified results
    # over the request play
    e.request._transaction_properties = {}
