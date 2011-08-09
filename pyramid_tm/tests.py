import unittest
from transaction import TransactionManager

class TestDefaultCommitVeto(unittest.TestCase):
    def _callFUT(self, response, request=None):
        from pyramid_tm import default_commit_veto
        return default_commit_veto(request, response)

    def test_it_true_500(self):
        response = DummyResponse('500 Server Error')
        self.failUnless(self._callFUT(response))

    def test_it_true_503(self):
        response = DummyResponse('503 Service Unavailable')
        self.failUnless(self._callFUT(response))

    def test_it_true_400(self):
        response = DummyResponse('400 Bad Request')
        self.failUnless(self._callFUT(response))

    def test_it_true_411(self):
        response = DummyResponse('411 Length Required')
        self.failUnless(self._callFUT(response))

    def test_it_false_200(self):
        response = DummyResponse('200 OK')
        self.failIf(self._callFUT(response))

    def test_it_false_201(self):
        response = DummyResponse('201 Created')
        self.failIf(self._callFUT(response))

    def test_it_false_301(self):
        response = DummyResponse('301 Moved Permanently')
        self.failIf(self._callFUT(response))

    def test_it_false_302(self):
        response = DummyResponse('302 Found')
        self.failIf(self._callFUT(response))

    def test_it_false_x_tm_commit(self):
        response = DummyResponse('200 OK', {'x-tm':'commit'})
        self.failIf(self._callFUT(response))

    def test_it_true_x_tm_abort(self):
        response = DummyResponse('200 OK', {'x-tm':'abort'})
        self.failUnless(self._callFUT(response))

    def test_it_true_x_tm_anythingelse(self):
        response = DummyResponse('200 OK', {'x-tm':''})
        self.failUnless(self._callFUT(response))

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
        
    def test_handler_isdoomed(self):
        txn = DummyTransaction(True)
        self._callFUT(txn=txn)
        self.assertTrue(txn.began)
        self.assertTrue(txn.aborted)
        self.assertFalse(txn.committed)

    def test_default_commit_veto(self):
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
        registry = DummyRegistry({'pyramid_tm.commit_veto':None})
        result = self._callFUT(handler=handler, registry=registry)
        self.assertEqual(result, response)
        self.assertTrue(self.txn.began)
        self.assertFalse(self.txn.aborted)
        self.assertTrue(self.txn.committed)

    def test_commit_veto_true(self):
        registry = DummyRegistry(
            {'pyramid_tm.commit_veto':'pyramid_tm.tests.veto_true'})
        result = self._callFUT(registry=registry)
        self.assertEqual(result, self.response)
        self.assertTrue(self.txn.began)
        self.assertTrue(self.txn.aborted)
        self.assertFalse(self.txn.committed)

    def test_commit_veto_false(self):
        registry = DummyRegistry(
            {'pyramid_tm.commit_veto':'pyramid_tm.tests.veto_false'})
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

def veto_true(request, response):
    return True

def veto_false(request, response):
    return False


class Test_includeme(unittest.TestCase):
    def test_it(self):
        from pyramid_tm import includeme
        config = DummyConfig()
        includeme(config)
        self.assertEqual(len(config.tweens), 1)


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

    def __init__(self, doomed=False):
        self.doomed = doomed

    def isDoomed(self):
        return self.doomed

    def get(self):
        return self

    def begin(self):
        self.began = True
        return self

    def commit(self):
        self.committed = True

    def abort(self):
        self.aborted = True

class DummyRequest(object):
    def __init__(self):
        self.environ = {}

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

    def add_tween(self, x, above=None, below=None):
        self.tweens.append((x, above, below))
