from data_preprocessor.operation import Operation
from typing import Union, final
import data_preprocessor.data as data


class InputOperation(Operation):
    """
    Base class for operations to be used to provide input
    These operations must not change the shape
    """

    @final
    def getOutputShape(self) -> Union[data.Shape, None]:
        return self._shape

    @staticmethod
    @final
    def isOutputShapeKnown() -> bool:
        return True

    @staticmethod
    def isInputOperation() -> bool:
        return True
