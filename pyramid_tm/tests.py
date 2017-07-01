# -*- coding: utf-8 -*-

import functools
import unittest
import transaction
from transaction import TransactionManager
from pyramid import testing
from webtest import TestApp

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
        self.config = testing.setUp(request=self.request)
        self.registry = self.config.registry
        self.settings = self.registry.settings

    def tearDown(self):
        testing.tearDown()

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
        request.tm = txn
        from pyramid_tm import tm_tween_factory
        factory = tm_tween_factory(handler, registry)
        return factory(request)

    def test_repoze_tm_active(self):
        request = DummyRequest()
        request.environ['repoze.tm.active'] = True
        result = self._callFUT(request=request)
        self.assertEqual(result, self.response)
        self.assertFalse(self.txn.began)

    def test_tm_active(self):
        request = DummyRequest()
        request.environ['tm.active'] = True
        result = self._callFUT(request=request)
        self.assertEqual(result, self.response)
        self.assertFalse(self.txn.began)

    def test_should_activate_true(self):
        self.settings.update(
            {'tm.activate_hook':'pyramid_tm.tests.activate_true'})
        result = self._callFUT()
        self.assertEqual(result, self.response)
        self.assertTrue(self.txn.began)

    def test_should_activate_false(self):
        self.settings.update(
            {'tm.activate_hook':'pyramid_tm.tests.activate_false'})
        result = self._callFUT()
        self.assertEqual(result, self.response)
        self.assertFalse(self.txn.began)

    def test_handler_exception(self):
        def handler(request):
            raise NotImplementedError
        self.assertRaises(NotImplementedError, self._callFUT, handler=handler)
        self.assertTrue(self.txn.began)
        self.assertTrue(self.txn.aborted)
        self.assertFalse(self.txn.committed)

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

    def test_handler_w_native_unauthenticated_userid(self):
        self.config.testing_securitypolicy(userid='phred')
        self._callFUT()
        self.assertEqual(self.txn.user, u'phred')

    def test_handler_w_utf8_unauthenticated_userid(self):
        USERID = b'phred/\xd1\x80\xd0\xb5\xd1\x81'.decode('utf-8')
        self.config.testing_securitypolicy(userid=USERID)
        self._callFUT()
        self.assertEqual(self.txn.user, u'phred/рес')

    def test_handler_w_latin1_unauthenticated_userid(self):
        USERID = b'\xc4\xd6\xdc'
        self.config.testing_securitypolicy(userid=USERID)
        self._callFUT()
        self.assertEqual(self.txn.user, u'ÄÖÜ')

    def test_handler_w_integer_unauthenticated_userid(self):
        # See https://github.com/Pylons/pyramid_tm/issues/28
        USERID = 1234
        self.config.testing_securitypolicy(userid=USERID)
        self._callFUT()
        self.assertEqual(self.txn.user, u'1234')

    def test_disables_user_annotation(self):
        self.config.testing_securitypolicy(userid="nope")
        self.settings['tm.annotate_user'] = 'false'
        result = self._callFUT()
        self.assertEqual(self.txn.user, None)

    def test_handler_notes(self):
        self._callFUT()
        self.assertEqual(self.txn._note, '/')
        self.assertEqual(self.txn.user, None)

    def test_handler_notes_unicode_decode_error(self):
        class DummierRequest(DummyRequest):
            def _get_path_info(self):
                b"\xc0".decode("utf-8")
            def _set_path_info(self, val):
                pass
            path_info = property(_get_path_info, _set_path_info)

        request = DummierRequest()

        self._callFUT(request=request)
        self.assertEqual(self.txn._note, u'Unable to decode path as unicode')
        self.assertEqual(self.txn.user, None)

    def test_handler_notes_unicode_path(self):
        class DummierRequest(DummyRequest):

            def _get_path_info(self):
                return b'collection/\xd1\x80\xd0\xb5\xd1\x81'.decode('utf-8')

            def _set_path_info(self, val):
                pass

            path_info = property(_get_path_info, _set_path_info)

        request = DummierRequest()
        self._callFUT(request=request)
        self.assertEqual(self.txn._note, u'collection/рес')
        self.assertEqual(self.txn.user, None)

    def test_handler_notes_native_str_path(self):
        class DummierRequest(DummyRequest):

            def _get_path_info(self):
                return u'some/resource'

            def _set_path_info(self, val):
                pass

            path_info = property(_get_path_info, _set_path_info)

        request = DummierRequest()
        self._callFUT(request=request)
        self.assertEqual(self.txn._note, u'some/resource')
        self.assertEqual(self.txn.user, None)

    def test_active_flag_set_during_handler(self):
        result = []
        def handler(request):
            if 'tm.active' in request.environ:
                result.append('active')
            return self.response
        self._callFUT(handler=handler)
        self.assertEqual(result, ['active'])

    def test_active_flag_not_set_activate_false(self):
        self.settings.update(
            {'tm.activate_hook':'pyramid_tm.tests.activate_false'})
        result = []
        def handler(request):
            if 'tm.active' not in request.environ:
                result.append('not active')
            return self.response
        self._callFUT(handler=handler)
        self.assertEqual(result, ['not active'])

    def test_active_flag_unset_on_egress(self):
        self._callFUT()
        self.assertTrue('tm.active' not in self.request.environ)

    def test_active_flag_unset_on_egress_abort(self):
        txn = DummyTransaction(doomed=True)
        self._callFUT(txn=txn)
        self.assertTrue('tm.active' not in self.request.environ)

    def test_active_flag_unset_on_egress_exception(self):
        def handler(request):
            raise NotImplementedError
        try:
            self._callFUT(handler=handler)
        except NotImplementedError:
            pass
        self.assertTrue('tm.active' not in self.request.environ)

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
        self.settings.update({'tm.commit_veto':None})
        result = self._callFUT(handler=handler)
        self.assertEqual(result, response)
        self.assertTrue(self.txn.began)
        self.assertFalse(self.txn.aborted)
        self.assertTrue(self.txn.committed)

    def test_commit_veto_true(self):
        self.settings.update({'tm.commit_veto':'pyramid_tm.tests.veto_true'})
        result = self._callFUT()
        self.assertEqual(result, self.response)
        self.assertTrue(self.txn.began)
        self.assertTrue(self.txn.aborted)
        self.assertFalse(self.txn.committed)

    def test_commit_veto_false(self):
        self.settings.update({'tm.commit_veto':'pyramid_tm.tests.veto_false'})
        result = self._callFUT()
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
        self.settings.update(
            {'pyramid_tm.commit_veto':'pyramid_tm.tests.veto_true'})
        result = self._callFUT()
        self.assertEqual(result, self.response)
        self.assertTrue(self.txn.began)
        self.assertTrue(self.txn.aborted)
        self.assertFalse(self.txn.committed)

class Test_create_tm(unittest.TestCase):

    def setUp(self):
        self.request = DummyRequest()
        self.request.registry = Dummy(settings={})
        # Get rid of the request.tm attribute since it shouldn't be here yet.
        del self.request.tm


    def tearDown(self):
        testing.tearDown()

    def _callFUT(self, request=None):
        if request is None:
            request = self.request
        from pyramid_tm import create_tm
        return create_tm(request)

    def test_default_threadlocal(self):
        self.assertTrue(self._callFUT() is transaction.manager)

    def test_overridden_manager(self):
        txn = DummyTransaction()
        self.request.registry.settings["tm.manager_hook"] = lambda r: txn
        self.assertTrue(self._callFUT() is txn)

def veto_true(request, response):
    return True

def veto_false(request, response):
    return False

def activate_true(request):
    return True

def activate_false(request):
    return False

create_manager = None

class Test_includeme(unittest.TestCase):
    def test_it(self):
        from pyramid.tweens import EXCVIEW
        from pyramid_tm import includeme, create_tm, TMActivePredicate
        config = DummyConfig()
        includeme(config)
        self.assertEqual(config.tweens,
                         [('pyramid_tm.tm_tween_factory', None, EXCVIEW)])
        self.assertEqual(config.request_methods,
                         [(create_tm, 'tm', True)])
        self.assertEqual(config.view_predicates,
                         [('tm_active', TMActivePredicate)])
        self.assertEqual(len(config.actions), 1)
        self.assertEqual(config.actions[0][0], None)
        self.assertEqual(config.actions[0][2], 10)

    def test_invalid_dotted(self):
        from pyramid_tm import includeme
        config = DummyConfig()
        config.registry.settings["tm.manager_hook"] = "an.invalid.import"
        includeme(config)
        self.assertRaises(ImportError, config.actions[0][1])

    def test_valid_dotted(self):
        from pyramid_tm import includeme
        config = DummyConfig()
        config.registry.settings["tm.manager_hook"] = \
            "pyramid_tm.tests.create_manager"
        includeme(config)
        config.actions[0][1]()
        self.assertTrue(
            config.registry.settings["tm.manager_hook"] is create_manager
        )

    def test_it_config(self):
        config = testing.setUp()
        try:
            config.include('pyramid_tm')
        finally:
            testing.tearDown()

def skip_if_missing(module):  # pragma: no cover
    def wrapper(fn):
        try:
            __import__(module)
        except ImportError:
            return

        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            return fn(*args, **kwargs)
        return wrapped
    return wrapper

def skip_if_package_lt(pkg, version):  # pragma: no cover
    import pkg_resources
    def wrapper(fn):
        dist = pkg_resources.get_distribution(pkg)
        if dist.parsed_version < pkg_resources.parse_version(version):
            return

        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            return fn(*args, **kwargs)
        return wrapped
    return wrapper

class TestIntegration(unittest.TestCase):
    def setUp(self):
        self.config = testing.setUp(autocommit=False)
        self.config.include('pyramid_tm')

    def tearDown(self):
        testing.tearDown()

    def _makeApp(self):
        app = self.config.make_wsgi_app()
        return TestApp(app)

    def test_it(self):
        config = self.config
        dm = DummyDataManager()
        def view(request):
            dm.bind(request.tm)
            return 'ok'
        config.add_view(view, name='', renderer='string')
        app = self._makeApp()
        resp = app.get('/')
        self.assertEqual(resp.body, b'ok')
        self.assertEqual(dm.action, 'commit')

    @skip_if_missing('pyramid_retry')
    def test_transient_error_is_retried(self):
        from transaction.interfaces import TransientError
        config = self.config
        config.add_settings({'retry.attempts': 2})
        config.include('pyramid_retry')
        class Conflict(TransientError):
            pass
        calls = []
        def view(request):
            dm = DummyDataManager()
            dm.bind(request.tm)
            if len(calls) < 1:
                calls.append('fail')
                raise Conflict
            calls.append('ok')
            return 'ok'
        config.add_view(view, renderer='string')
        app = self._makeApp()
        result = app.get('/')
        self.assertEqual(calls, ['fail', 'ok'])
        self.assertEqual(result.body, b'ok')

    def test_unhandled_error_aborts(self):
        config = self.config
        dm = DummyDataManager()
        def view(request):
            dm.bind(request.tm)
            raise ValueError
        config.add_view(view)
        app = self._makeApp()
        self.assertRaises(ValueError, app.get, '/')
        self.assertEqual(dm.action, 'abort')

    def test_handled_error_aborts(self):
        config = self.config
        dm = DummyDataManager()
        def view(request):
            dm.bind(request.tm)
            raise ValueError
        config.add_view(view)
        def exc_view(request):
            return 'failure'
        config.add_view(exc_view, context=ValueError, renderer='string')
        app = self._makeApp()
        resp = app.get('/')
        self.assertEqual(resp.body, b'failure')
        self.assertEqual(dm.action, 'abort')

    def test_handled_error_commits_with_veto(self):
        config = self.config
        dm = DummyDataManager()
        def view(request):
            dm.bind(request.tm)
            raise ValueError
        config.add_view(view)
        def exc_view(request):
            return 'failure'
        def commit_veto(request, response):
            return request.exception is None
        config.add_settings({'tm.commit_veto': commit_veto})
        config.add_view(exc_view, context=ValueError, renderer='string')
        app = self._makeApp()
        resp = app.get('/')
        self.assertEqual(resp.body, b'failure')
        self.assertEqual(dm.action, 'commit')

    def test_explicit_manager_fails_before_tm(self):
        from transaction.interfaces import NoTransaction
        config = self.config
        config.add_settings({'tm.manager_hook': 'pyramid_tm.explicit_manager'})
        config.add_tween('pyramid_tm.tests.dummy_tween_factory',
                         over='pyramid_tm.tm_tween_factory')
        dm = DummyDataManager()
        def dummy_handler(handler, request):
            dm.bind(request.tm)
        config.registry['dummy_handler'] = dummy_handler
        config.add_view(lambda r: r.response)
        app = self._makeApp()
        self.assertRaises(NoTransaction, app.get, '/')

    def test_explicit_manager_fails_after_tm(self):
        from transaction.interfaces import NoTransaction
        config = self.config
        config.add_settings({'tm.manager_hook': 'pyramid_tm.explicit_manager'})
        config.add_tween('pyramid_tm.tests.dummy_tween_factory',
                         over='pyramid_tm.tm_tween_factory')
        dm = DummyDataManager()
        def dummy_handler(handler, request):
            handler(request)
            dm.bind(request.tm)
        config.registry['dummy_handler'] = dummy_handler
        config.add_view(lambda r: r.response)
        app = self._makeApp()
        self.assertRaises(NoTransaction, app.get, '/')

    def test_explicit_manager_works_in_view(self):
        config = self.config
        dm = DummyDataManager()
        def view(request):
            dm.bind(request.tm)
            return 'ok'
        config.add_view(view, renderer='string')
        app = self._makeApp()
        resp = app.get('/')
        self.assertEqual(resp.body, b'ok')
        self.assertEqual(dm.action, 'commit')

    def test_tm_active_predicate_is_True(self):
        config = self.config
        dm = DummyDataManager()
        def true_view(request):
            dm.bind(request.tm)
            return 'ok'
        def false_view(request):  # pragma: no cover
            raise RuntimeError
        config.add_view(true_view, tm_active=True, renderer='string')
        config.add_view(false_view, tm_active=False, renderer='string')
        app = self._makeApp()
        resp = app.get('/')
        self.assertEqual(resp.body, b'ok')
        self.assertEqual(dm.action, 'commit')

    def test_tm_active_predicate_is_False(self):
        config = self.config
        config.add_settings({'tm.activate_hook': activate_false})
        def true_view(request):  # pragma: no cover
            raise RuntimeError
        def false_view(request):
            return 'ok'
        config.add_view(true_view, tm_active=True, renderer='string')
        config.add_view(false_view, tm_active=False, renderer='string')
        app = self._makeApp()
        resp = app.get('/')
        self.assertEqual(resp.body, b'ok')

    def test_tm_active_predicate_is_bool(self):
        from pyramid.exceptions import ConfigurationError
        config = self.config
        try:
            view = lambda r: 'ok'
            config.add_view(view, tm_active='yes', renderer='string')
            config.commit()
        except ConfigurationError:
            pass
        else:  # pragma: no cover
            raise AssertionError

    @skip_if_package_lt('pyramid', '1.7')
    def test_excview_rendered_after_failed_commit(self):
        config = self.config
        tm = DummyTransaction(finish_with_exc=ValueError)
        config.add_settings({'tm.manager_hook': lambda r: tm})
        config.add_view(lambda r: 'ok', renderer='string')
        def exc_view(request):
            return 'failure'
        config.add_view(exc_view, context=ValueError, renderer='string')
        app = self._makeApp()
        resp = app.get('/')
        self.assertEqual(resp.body, b'failure')

    @skip_if_package_lt('pyramid', '1.7')
    def test_excview_rendered_after_failed_abort(self):
        config = self.config
        tm = DummyTransaction(finish_with_exc=ValueError)
        config.add_settings({'tm.manager_hook': lambda r: tm})
        config.add_settings({'tm.commit_veto': lambda req, resp: True})
        config.add_view(lambda r: 'ok', renderer='string')
        def exc_view(request):
            return 'failure'
        config.add_view(exc_view, context=ValueError, renderer='string')
        app = self._makeApp()
        resp = app.get('/')
        self.assertEqual(resp.body, b'failure')

    @skip_if_package_lt('pyramid', '1.7')
    def test_excview_rendered_after_failed_abort_from_uncaught_exc(self):
        config = self.config
        tm = DummyTransaction(finish_with_exc=ValueError)
        config.add_settings({'tm.manager_hook': lambda r: tm})
        def view(request):
            raise RuntimeError
        config.add_view(view)
        def exc_view(request):
            return 'failure'
        config.add_view(exc_view, context=ValueError, renderer='string')
        app = self._makeApp()
        resp = app.get('/')
        self.assertEqual(resp.body, b'failure')

    def test_failed_commit_reraises(self):
        config = self.config
        tm = DummyTransaction(finish_with_exc=ValueError)
        config.add_settings({'tm.manager_hook': lambda r: tm})
        config.add_view(lambda r: 'ok', renderer='string')
        app = self._makeApp()
        self.assertRaises(ValueError, lambda: app.get('/'))

    def test_failed_abort_reraises(self):
        config = self.config
        tm = DummyTransaction(finish_with_exc=ValueError)
        config.add_settings({'tm.manager_hook': lambda r: tm})
        config.add_settings({'tm.commit_veto': lambda req, resp: True})
        config.add_view(lambda r: 'ok', renderer='string')
        app = self._makeApp()
        self.assertRaises(ValueError, lambda: app.get('/'))


class Dummy(object):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

class DummyTransaction(TransactionManager):
    began = False
    committed = False
    aborted = False
    _resources = []
    user = None

    def __init__(self, doomed=False, retryable=False, finish_with_exc=None):
        self.doomed = doomed
        self.began = 0
        self.committed = 0
        self.aborted = 0
        self.retryable = retryable
        self.active = False
        self.finish_with_exc = finish_with_exc

    def _retryable(self, t, v):
        if self.active:
            return self.retryable

    def get(self): # pragma: no cover
        return self

    def isDoomed(self):
        return self.doomed

    def begin(self):
        self.began+=1
        self.active = True
        return self

    def commit(self):
        self.committed+=1
        if self.finish_with_exc:
            raise self.finish_with_exc

    def abort(self):
        self.active = False
        self.aborted+=1
        if self.finish_with_exc:
            raise self.finish_with_exc

    def note(self, value):
        self._note = value

class DummyDataManager(object):
    action = None

    def bind(self, tm):
        self.transaction_manager = tm
        tm.get().join(self)

    def abort(self, transaction):
        self.action = 'abort'

    def tpc_begin(self, transaction):
        pass

    def commit(self, transaction):
        self.action = 'commit'

    def tpc_vote(self, transaction):
        pass

    def tpc_finish(self, transaction):
        pass

    def tpc_abort(self, transaction): # pragma: no cover
        pass

    def sortKey(self):
        return 'dummy:%s' % id(self)

class DummyRequest(testing.DummyRequest):
    def __init__(self, *args, **kwargs):
        self.tm = TransactionManager()
        super(DummyRequest, self).__init__(self, *args, **kwargs)

    def invoke_subrequest(self, request, use_tweens): # pragma: no cover
        pass

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
        self.request_methods = []
        self.view_predicates = []
        self.actions = []

    def add_tween(self, x, under=None, over=None):
        self.tweens.append((x, under, over))

    def add_request_method(self, x, name=None, reify=None):
        self.request_methods.append((x, name, reify))

    def add_view_predicate(self, name, obj):
        self.view_predicates.append((name, obj))

    def action(self, x, fun, order=None):
        self.actions.append((x, fun, order))

def dummy_tween_factory(handler, registry):
    def dummy_tween(request):
        dummy_handler = registry['dummy_handler']
        return dummy_handler(handler, request)
    return dummy_tween
