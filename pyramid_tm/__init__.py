import pyramid.events

import transaction


def default_commit_veto(environ, status, headers):
    '''A commit_veto that will abort the transaction
    if the status response starts with 4 or 5.  Will also
    abort if there is a x-tm-abort header.
    '''

    for bad in ('4', '5'):
        if status.startswith(bad):
            return True

    for header_name, header_value in headers:
        if header_name.lower() == 'x-tm-abort':
            return True


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
