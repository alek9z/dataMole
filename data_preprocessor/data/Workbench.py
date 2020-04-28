from typing import Dict

import data_preprocessor.data as data


class Workbench:
    """ Dict-like object keeping track of every data.Frame """

    def __init__(self):
        self.__frames: Dict[str, data.Frame] = dict()

    def __getitem__(self, name: str) -> data.Frame:
        return self.__frames[name]

    def __setitem__(self, name: str, value: data.Frame) -> None:
        if name in self.__frames.keys():
            raise KeyError('Duplicate variable name is not allowed')
        self.__frames[name] = value

    def __delitem__(self, name: str) -> None:
        self.__frames.__delitem__(name)

    def __len__(self) -> int:
        return len(self.__frames)
