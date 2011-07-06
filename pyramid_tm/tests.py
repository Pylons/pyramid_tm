import unittest


class TestDefaultCommitVeto(unittest.TestCase):

    def _callFUT(self, status, headers=()):
        from pyramid_tm import default_commit_veto
        return default_commit_veto(None, status, headers)

    def test_it_true_5XX(self):
        self.failUnless(self._callFUT('500 Server Error'))
        self.failUnless(self._callFUT('503 Service Unavailable'))

    def test_it_true_4XX(self):
        self.failUnless(self._callFUT('400 Bad Request'))
        self.failUnless(self._callFUT('411 Length Required'))

    def test_it_false_2XX(self):
        self.failIf(self._callFUT('200 OK'))
        self.failIf(self._callFUT('201 Created'))

    def test_it_false_3XX(self):
        self.failIf(self._callFUT('301 Moved Permanently'))
        self.failIf(self._callFUT('302 Found'))

    def test_it_true_x_tm_abort_specific(self):
        self.failUnless(self._callFUT('200 OK', [('X-Tm-Abort', True)]))

    def test_it_false_x_tm_commit(self):
        self.failIf(self._callFUT('200 OK', [('X-Tm', 'commit')]))

    def test_it_true_x_tm_abort(self):
        self.failUnless(self._callFUT('200 OK', [('X-Tm', 'abort')]))

    def test_it_true_x_tm_anythingelse(self):
        self.failUnless(self._callFUT('200 OK', [('X-Tm', '')]))

    def test_x_tm_generic_precedes_x_tm_abort_specific(self):
        self.failIf(self._callFUT('200 OK', [('X-Tm', 'commit'),
                                             ('X-Tm-Abort', True)]))


class TestTMSubscriber(unittest.TestCase):

    def setUp(self):
        from pyramid_tm import TMSubscriber
        self.subscriber = TMSubscriber(None)
        self.subscriber.transaction = MockTransaction()

    def test_basics(self):
        subscriber = self.subscriber
        transaction = subscriber.transaction

        subscriber.begin()
        self.assertTrue(transaction.began)

        subscriber.commit()
        self.assertTrue(transaction.committed)

        subscriber.abort()
        self.assertTrue(transaction.aborted)

    def test_calling(self):
        subscriber = self.subscriber

        # no callbacks should be registered if it thinks repoze.tm is alive
        m = Mock(request=MockRequest())
        m.request.environ['repoze.tm.active'] = True
        subscriber(m)
        self.assertEqual(len(m.request.finished_callbacks), 0)

        # with repoze.tm not alive, we should get regular callbacks
        del m.request.environ['repoze.tm.active']
        subscriber(m)
        self.assertEqual(len(m.request.finished_callbacks), 1)
        self.assertEqual(len(m.request.response_callbacks), 1)

    def build_reqres(self):
        response = Mock(status='100', headerlist=[])
        request = Mock(exception=None, environ={})
        return request, response

    def test_process_commit(self):
        subscriber = self.subscriber
        subscriber.commit_veto = lambda x, y, z: None
        request, response = self.build_reqres()
        subscriber.process(request, response)
        self.assertTrue(hasattr(request, '_transaction_committed'))
        self.assertTrue(subscriber.transaction.committed)

    def test_process_bypass(self):
        subscriber = self.subscriber
        request, response = self.build_reqres()
        subscriber.process(request, response)
        self.assertTrue(hasattr(request, '_transaction_committed'))
        self.assertFalse(subscriber.process(request, response))

    def test_process_abort1(self):
        request, response = self.build_reqres()
        subscriber = self.subscriber
        subscriber.transaction.isDoomed = lambda: True
        subscriber.process(request, response)
        self.assertTrue(hasattr(request, '_transaction_committed'))
        self.assertTrue(self.subscriber.transaction.aborted)

    def test_process_abort2(self):
        request, response = self.build_reqres()
        subscriber = self.subscriber
        request.exception = Mock()
        subscriber.process(request, response)
        self.assertTrue(hasattr(request, '_transaction_committed'))
        self.assertTrue(self.subscriber.transaction.aborted)

    def test_process_abort3(self):
        request, response = self.build_reqres()
        subscriber = self.subscriber
        subscriber.commit_veto = lambda x, y, z: True
        request = Mock(exception=None, environ={})
        subscriber.process(request, response)
        self.assertTrue(hasattr(request, '_transaction_committed'))
        self.assertTrue(subscriber.transaction.aborted)


class TestIncludeMe(unittest.TestCase):

    def test_it(self):
        from pyramid_tm import includeme

        m = MockConfig()
        includeme(m)
        self.assertEqual(len(m.subscribers), 1)


class Mock(object):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class MockTransaction(object):
    began = False
    committed = False
    aborted = False

    def begin(self):
        self.began = True

    def get(self):
        return self

    def commit(self):
        self.committed = True

    def abort(self):
        self.aborted = True


class MockRequest(object):

    def __init__(self):
        self.environ = {}
        self.finished_callbacks = []
        self.response_callbacks = []

    def add_finished_callback(self, cb):
        self.finished_callbacks.append(cb)

    def add_response_callback(self, cb):
        self.response_callbacks.append(cb)


class MockConfig(object):
    def __init__(self):
        self.registry = Mock(settings={})
        self.subscribers = []

    def maybe_dotted(self, x):
        return x

    def add_subscriber(self, x, y):
        self.subscribers.append((x, y))
