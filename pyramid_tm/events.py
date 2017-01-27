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


class TransactionAborted(object):
    """We run out of attempts and the request could not be successfully played.

    This event is fired after the transaction has been rolled back. Any access to transaction aware databases should be avoided after this event.
    """

    def __init__(self, request, tx):
        self.request = request
        self.tx = tx
