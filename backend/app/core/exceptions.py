"""
自定义异常类
定义应用中使用的各种业务异常
"""


class PlatformAPIError(Exception):
    """
    平台 API 错误
    当调用域名注册商 API 失败时抛出
    """

    def __init__(self, platform: str, code: str, message: str):
        self.platform = platform
        self.code = code
        self.message = message
        super().__init__(f"[{platform}] {code}: {message}")


class AuthenticationError(Exception):
    """
    认证错误
    当用户认证失败时抛出
    """
    pass


class PermissionDeniedError(Exception):
    """
    权限不足错误
    当用户没有足够权限执行操作时抛出
    """
    pass


class NotFoundError(Exception):
    """
    资源未找到错误
    当请求的资源不存在时抛出
    """
    pass
