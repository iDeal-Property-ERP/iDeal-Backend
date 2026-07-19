import time
from functools import wraps
from http import HTTPStatus

from django.core.cache import cache
from django.utils.translation import gettext_lazy as _

def rate_limit(requests: int, window_seconds: int):
    """
    Strict rate-limiting decorator for API controllers.
    Limits the number of requests per IP address within the given time window.
    Assumes it wraps a method of a BaseController (e.g., post(self)).
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # Get client IP address
            ip = self.request.META.get("HTTP_X_FORWARDED_FOR")
            if ip:
                ip = ip.split(",")[0].strip()
            else:
                ip = self.request.META.get("REMOTE_ADDR", "unknown-ip")
            
            # Create a cache key unique to this view and IP
            cache_key = f"rl:{self.__class__.__name__}:{ip}"
            
            # Simple rate limiting using Redis list of timestamps or counter
            current_count = cache.get(cache_key)
            if current_count is None:
                cache.set(cache_key, 1, window_seconds)
            elif current_count >= requests:
                # Rate limit exceeded!
                return self.fail(
                    error="rate_limit_exceeded",
                    message=str(_("Too many requests. Please try again later.")),
                    status_code=HTTPStatus.TOO_MANY_REQUESTS
                )
            else:
                cache.incr(cache_key)
                
            return func(self, *args, **kwargs)
            
        return wrapper
    return decorator
