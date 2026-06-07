from dmr.errors import global_error_handler as dmr_global_error_handler


def global_error_handler(endpoint, controller, exc):
    return dmr_global_error_handler(endpoint, controller, exc)
