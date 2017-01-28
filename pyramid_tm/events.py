"""Transaction management related Pyramid events."""


class TransactionAttempt(object):
    """A web serving play will be attempted for a HTTP request.

    This event is fired just before the tween enters to request handling.

    * ``attempt_no == 0`` first attempt

    * ``attempt_no > 0`` any subsequent attempts

    :param request: Pyramid HTTP request object

    :param tx: :py:class:`transaction.Transaction` object

    :param attempt_no: Integer, 0 is the first request play attempt

    :param attempts: Total number of attempts before pyramid_tm gives up
    """

    def __init__(self, request, tx, attempt_no, attempts):
        self.request = request
        self.tx = tx
        self.attempt_no = attempt_no
        self.attempts = attempts



class TransactionExceptionRender(object):
    """Triggered before the exception view rendering starts."""

    def __init__(self, request, exc_info):
        self.request = request
        self.exc_info = exc_info