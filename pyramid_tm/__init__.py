import pyramid.events

import transaction


def default_commit_veto(environ, status, headers):
    '''When used as a commit veto, the logic in this function will cause the
    transaction to be committed if:

    - An ``X-Tm`` header with the value ``commit`` exists.

    If an ``X-Tm`` header with the value ``commit`` does not exist, the
    transaction will be aborted, if:

    - An ``X-Tm`` header with the value ``abort`` (or any value other than
      ``commit``) exists.

    - An ``X-Tm-Abort`` header exists with any value (for backwards
      compatability; prefer ``X-Tm=abort`` in new code).

    - The status code starts with ``4`` or ``5``.

    Otherwise the transaction will be committed by default.
    '''

    abort_compat = False
    for header_name, header_value in headers:
        header_name = header_name.lower()
        if header_name == 'x-tm':
            if header_value.lower() == 'commit':
                return False
            return True
        # x-tm honored before x-tm-abort compatability
        elif header_name == 'x-tm-abort':
            abort_compat = True
    if abort_compat:
        return True
    for bad in ('4', '5'):
        if status.startswith(bad):
            return True
    return False


class TMSubscriber(object):
    '''A NewRequest subscriber that knows about commit_veto.
    '''

    transaction = staticmethod(transaction)

    def __init__(self, commit_veto):
        self.commit_veto = commit_veto

    def __call__(self, event):
        if 'repoze.tm.active' in event.request.environ:
            return

        self.begin()
        event.request.add_finished_callback(self.process)
        event.request.add_response_callback(self.process)

    def begin(self):
        self.transaction.begin()

    def commit(self):
        self.transaction.get().commit()

    def abort(self):
        self.transaction.get().abort()

    def process(self, request, response=None):
        if getattr(request, '_transaction_committed', False):
            return False

        request._transaction_committed = True
        transaction = self.transaction

        # ZODB 3.8 + has isDoomed
        if hasattr(transaction, 'isDoomed') and transaction.isDoomed():
            return self.abort()

        if request.exception is not None:
            return self.abort()

        if response is not None and self.commit_veto is not None:
            environ = request.environ
            status, headers = response.status, response.headerlist

            if self.commit_veto(environ, status, headers):
                return self.abort()

        return self.commit()


def includeme(config):
    '''Setup the NewRequest subscriber for bootstrapping transactions.
    '''

    commit_veto = config.registry.settings.get('pyramid_tm.commit_veto',
                                               default_commit_veto)
    commit_veto = config.maybe_dotted(commit_veto)
    subscriber = TMSubscriber(commit_veto)
    config.add_subscriber(subscriber, pyramid.events.NewRequest)
