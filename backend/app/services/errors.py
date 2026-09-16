class ServiceError(Exception):
    """Domain error; `message` is safe to show to end users (PRD §16).

    Routes let these propagate; the app-level handler in main.py turns them into
    `{"detail": message}` responses with `status_code`.
    """

    status_code = 400
    message = "Something went wrong."

    def __init__(self, message: str | None = None) -> None:
        if message is not None:
            self.message = message
        super().__init__(self.message)


class NotFound(ServiceError):
    status_code = 404
    message = "Not found."


class Conflict(ServiceError):
    status_code = 409
    message = "This change conflicts with existing data."
