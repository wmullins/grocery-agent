from __future__ import annotations


class RetailError(RuntimeError):
    pass


class AuthRequired(RetailError):
    pass


class RetailUnavailable(RetailError):
    pass


class UnsupportedRetailer(RetailError):
    pass


class RetailCommandError(RetailError):
    def __init__(self, message: str, *, stderr: str = "", returncode: int | None = None) -> None:
        super().__init__(message)
        self.stderr = stderr
        self.returncode = returncode
