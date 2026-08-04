class DomainError(Exception):
    "Базовый класс для всех нарушений"


class InsufficientBalanceError(DomainError):
    pass


class InvalidAmountError(DomainError):
    pass

class InvalidStateTransitionError(DomainError):
    pass

class ValidationError(DomainError):
    pass