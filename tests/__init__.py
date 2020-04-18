def veto_true(request, response):
    return True


def veto_false(request, response):
    return False


def activate_true(request):
    return True


def activate_false(request):
    return False


create_manager = None


def dummy_tween_factory(handler, registry):
    def dummy_tween(request):
        dummy_handler = registry['dummy_handler']
        return dummy_handler(handler, request)

    return dummy_tween
