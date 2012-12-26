import unittest
from transaction import TransactionManager

class TestDefaultCommitVeto(unittest.TestCase):
    def _callFUT(self, response, request=None):
        from pyramid_tm import default_commit_veto
        return default_commit_veto(request, response)

    def test_it_true_500(self):
        response = DummyResponse('500 Server Error')
        self.assertTrue(self._callFUT(response))

    def test_it_true_503(self):
        response = DummyResponse('503 Service Unavailable')
        self.assertTrue(self._callFUT(response))

    def test_it_true_400(self):
        response = DummyResponse('400 Bad Request')
        self.assertTrue(self._callFUT(response))

    def test_it_true_411(self):
        response = DummyResponse('411 Length Required')
        self.assertTrue(self._callFUT(response))

    def test_it_false_200(self):
        response = DummyResponse('200 OK')
        self.assertFalse(self._callFUT(response))

    def test_it_false_201(self):
        response = DummyResponse('201 Created')
        self.assertFalse(self._callFUT(response))

    def test_it_false_301(self):
        response = DummyResponse('301 Moved Permanently')
        self.assertFalse(self._callFUT(response))

    def test_it_false_302(self):
        response = DummyResponse('302 Found')
        self.assertFalse(self._callFUT(response))

    def test_it_false_x_tm_commit(self):
        response = DummyResponse('200 OK', {'x-tm':'commit'})
        self.assertFalse(self._callFUT(response))

    def test_it_true_x_tm_abort(self):
        response = DummyResponse('200 OK', {'x-tm':'abort'})
        self.assertTrue(self._callFUT(response))

    def test_it_true_x_tm_anythingelse(self):
        response = DummyResponse('200 OK', {'x-tm':''})
        self.assertTrue(self._callFUT(response))

class Test_tm_tween_factory(unittest.TestCase):
    def setUp(self):
        self.txn = DummyTransaction()
        self.request = DummyRequest()
        self.response = DummyResponse()
        self.registry = DummyRegistry()
        
    def _callFUT(self, handler=None, registry=None, request=None, txn=None):
        if handler is None:
            def handler(request):
                return self.response
        if registry is None:
            registry = self.registry
        if request is None:
            request = self.request
        if txn is None:
            txn = self.txn
        from pyramid_tm import tm_tween_factory
        factory = tm_tween_factory(handler, registry, txn)
        return factory(request)

    def test_repoze_tm_active(self):
        request = DummyRequest()
        request.environ['repoze.tm.active'] = True
        result = self._callFUT(request=request)
        self.assertEqual(result, self.response)
        self.assertFalse(self.txn.began)

    def test_handler_exception(self):
        def handler(request):
            raise NotImplementedError
        self.assertRaises(NotImplementedError, self._callFUT, handler=handler)
        self.assertTrue(self.txn.began)
        self.assertTrue(self.txn.aborted)
        self.assertFalse(self.txn.committed)

    def test_handler_retryable_exception(self):
        from transaction.interfaces import TransientError
        class Conflict(TransientError):
            pass
        count = []
        response = DummyResponse()
        self.registry.settings['tm.attempts'] = '3'
        def handler(request, count=count):
            count.append(True)
            if len(count) == 3:
                return response
            raise Conflict
        txn = DummyTransaction(retryable=True)
        result = self._callFUT(handler=handler, txn=txn)
        self.assertTrue(txn.began)
        self.assertEqual(txn.committed, 1)
        self.assertEqual(txn.aborted, 2)
        self.assertEqual(self.request.made_seekable, 3)
        self.assertEqual(result, response)

    def test_handler_retryable_exception_defaults_to_1(self):
        from transaction.interfaces import TransientError
        class Conflict(TransientError):
            pass
        count = []
        def handler(request, count=count):
            raise Conflict
        self.assertRaises(Conflict, self._callFUT, handler=handler)
        
    def test_handler_isdoomed(self):
        txn = DummyTransaction(True)
        self._callFUT(txn=txn)
        self.assertTrue(txn.began)
        self.assertTrue(txn.aborted)
        self.assertFalse(txn.committed)

    def test_500_without_commit_veto(self):
        response = DummyResponse()
        response.status = '500 Bad Request'
        def handler(request):
            return response
        result = self._callFUT(handler=handler)
        self.assertEqual(result, response)
        self.assertTrue(self.txn.began)
        self.assertFalse(self.txn.aborted)
        self.assertTrue(self.txn.committed)

    def test_500_with_default_commit_veto(self):
        settings = self.registry.settings
        settings['tm.commit_veto'] = 'pyramid_tm.default_commit_veto'
        response = DummyResponse()
        response.status = '500 Bad Request'
        def handler(request):
            return response
        result = self._callFUT(handler=handler)
        self.assertEqual(result, response)
        self.assertTrue(self.txn.began)
        self.assertTrue(self.txn.aborted)
        self.assertFalse(self.txn.committed)

    def test_null_commit_veto(self):
        response = DummyResponse()
        response.status = '500 Bad Request'
        def handler(request):
            return response
        registry = DummyRegistry({'tm.commit_veto':None})
        result = self._callFUT(handler=handler, registry=registry)
        self.assertEqual(result, response)
        self.assertTrue(self.txn.began)
        self.assertFalse(self.txn.aborted)
        self.assertTrue(self.txn.committed)

    def test_commit_veto_true(self):
        registry = DummyRegistry(
            {'tm.commit_veto':'pyramid_tm.tests.veto_true'})
        result = self._callFUT(registry=registry)
        self.assertEqual(result, self.response)
        self.assertTrue(self.txn.began)
        self.assertTrue(self.txn.aborted)
        self.assertFalse(self.txn.committed)

    def test_commit_veto_false(self):
        registry = DummyRegistry(
            {'tm.commit_veto':'pyramid_tm.tests.veto_false'})
        result = self._callFUT(registry=registry)
        self.assertEqual(result, self.response)
        self.assertTrue(self.txn.began)
        self.assertFalse(self.txn.aborted)
        self.assertTrue(self.txn.committed)

    def test_commitonly(self):
        result = self._callFUT()
        self.assertEqual(result, self.response)
        self.assertTrue(self.txn.began)
        self.assertFalse(self.txn.aborted)
        self.assertTrue(self.txn.committed)

    def test_commit_veto_alias(self):
        registry = DummyRegistry(
            {'pyramid_tm.commit_veto':'pyramid_tm.tests.veto_true'})
        result = self._callFUT(registry=registry)
        self.assertEqual(result, self.response)
        self.assertTrue(self.txn.began)
        self.assertTrue(self.txn.aborted)
        self.assertFalse(self.txn.committed)

def veto_true(request, response):
    return True

def veto_false(request, response):
    return False


class Test_includeme(unittest.TestCase):
    def test_it(self):
        from pyramid.tweens import EXCVIEW
        from pyramid_tm import includeme
        config = DummyConfig()
        includeme(config)
        self.assertEqual(config.tweens,
                         [('pyramid_tm.tm_tween_factory', EXCVIEW, None)])

class Dummy(object):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

class DummyRegistry(object):
    def __init__(self, settings=None):
        if settings is None:
            settings = {}
        self.settings = settings


class DummyTransaction(TransactionManager):
    began = False
    committed = False
    aborted = False
    _resources = []

    def __init__(self, doomed=False, retryable=False):
        self.doomed = doomed
        self.began = 0
        self.committed = 0
        self.aborted = 0
        self.retryable = retryable

    @property
    def manager(self):
        return self

    def _retryable(self, t, v):
        return self.retryable

    def isDoomed(self):
        return self.doomed

    def begin(self):
        self.began+=1
        return self

    def commit(self):
        self.committed+=1

    def abort(self):
        self.aborted+=1

class DummyRequest(object):
    def __init__(self):
        self.environ = {}
        self.made_seekable = 0

    def make_body_seekable(self):
        self.made_seekable += 1

class DummyResponse(object):
    def __init__(self, status='200 OK', headers=None):
        self.status = status
        if headers is None:
            headers = {}
        self.headers = headers

class DummyConfig(object):
    def __init__(self):
        self.registry = Dummy(settings={})
        self.tweens = []

    def add_tween(self, x, under=None, over=None):
        self.tweens.append((x, under, over))
