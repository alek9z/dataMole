# -*- coding: utf-8 -*-
#
# Author:       Alessandro Zangari (alessandro.zangari.code@outlook.com)
# Copyright:    © Copyright 2020 Alessandro Zangari, Università degli Studi di Padova
# License:      GPL-3.0-or-later
# Date:         2020-10-04
# Version:      1.0
#
# This file is part of DataMole.
#
# DataMole is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# any later version.
#
# DataMole is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with DataMole.  If not, see <https://www.gnu.org/licenses/>.

import re
from typing import List

import numpy as np
from PySide2.QtCore import QLocale
from PySide2.QtGui import QValidator, QIntValidator, QDoubleValidator


# doubleListValidator = QRegExpValidator(QRegExp('(\\d+(\\.\\d)?\\d*)(\\,\\s?(\\d+(\\.\\d)?\\d*))*'))


def numpy_equal(a: np.array, b: np.array) -> bool:
    return ((a == b) | ((a != a) & (b != b))).all()


def splitString(string: str, sep: str) -> List[str]:
    """
    Split a string on a separator, trimming spaces. Parts within double quotes are not parsed

    :param string: string to split
    :param sep: the separator string (or single char)

    :return: the list resulting from split

    """
    string = string.strip(' ')
    sepPattern = '\\s*{}\\s*'.format(sep)
    # Split on separator
    listS = re.split('({})(?=(?:"[^"]*"|[^"])*$)'.format(sepPattern), string)
    # Filter away separators
    listS = [s.strip('" \b') for s in listS if not re.fullmatch(sepPattern, s)]
    return listS


def joinList(values: List, sep: str) -> str:
    """
    Takes a list of values and a separator and returns a string with every value separated by a separator
    It's similar to str.join but takes care to add ' " ' around a value if it contains the separator

    :param values: values to join in a string
    :param sep: the string separator

    :return: the string representation of the list of values, with 'sep' as separator

    """
    result = list()
    for v in values:
        s: str
        if isinstance(v, str):
            if sep in v:
                s = '"{}"'.format(v)
            else:
                s = v.strip(' \b')
        else:
            s = str(v)
        result.append(s)
    return sep.join(result)


def parseNan(values: List):
    """
    Converts string values 'nan' as actual pandas nan values

    :param values: list-like object

    :return: new list with nan values

    """
    newValues = list()
    for el in values:
        if str(el).lower() == 'nan':
            el = np.nan
        newValues.append(el)
    return newValues


def isFloat(text: str) -> bool:
    """
    Return whether the provided text is a valid float

    :param text: the number as string

    :return:: True or False

    """
    try:
        float(text)
    except ValueError:
        return False
    else:
        return True


class NumericListValidator(QValidator):
    """
    QValidator for space-separated list of numbers. Works with float or ints
    """

    def __init__(self, float_int: type, parent=None):
        super().__init__(parent)
        if float_int is int:
            self.__numValidator = QIntValidator(self)
        elif float_int is float:
            self.__numValidator = QDoubleValidator(self)

    def validate(self, inputString: str, pos: int) -> QValidator.State:
        self.__numValidator.setLocale(QLocale(QLocale.English, QLocale.UnitedStates))
        inputString = inputString.strip(' ')
        stringList: List[str] = inputString.split(' ')
        for string in stringList:
            if self.__numValidator.validate(string, 0)[0] == QValidator.Invalid:
                return QValidator.Invalid
        return QValidator.Acceptable


class MixedListValidator(QValidator):
    # _regexp = QRegExp('((\\S+)|(\'.+\'))({}((\\S+)|(\'.+\')))*')

    def __init__(self, parent=None):
        super().__init__(parent)
        self.__regexp = '[^\']*'

    def validate(self, inputString: str, pos: int) -> QValidator.State:
        inputString = inputString.strip(' ')
        if re.fullmatch(self.__regexp, inputString):
            return QValidator.Acceptable
        else:
            match = re.match(self.__regexp, inputString)
            if match and len(match.group(0)) == len(inputString):
                return QValidator.Intermediate
        return QValidator.Invalid
        # if self._regexp.exactMatch(inputString):
        #     return QValidator.Acceptable
        # elif self._regexp.matchedLength() == len(inputString):
        #     return QValidator.Intermediate
        # pos = len(inputString)
        # return QValidator.Invalid


class ManyMixedListsValidator(QValidator):
    """
    Validates a list of lists, where each value in a list is space separated and every list is
    semicolon separated
    """

    def validate(self, inputString: str, pos: int) -> QValidator.State:
        inputString = inputString.strip(' ')
        lists = splitString(inputString, sep=';')
        val = MixedListValidator()
        for s in lists:
            if val.validate(s, 0) == QValidator.Invalid:
                return QValidator.Invalid
        return QValidator.Acceptable


class SingleStringValidator(QValidator):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.__regexp = '[^\'\b ]*'

    def validate(self, inputString: str, pos: int) -> QValidator.State:
        inputString = inputString.strip()
        if re.fullmatch(self.__regexp, inputString):
            return QValidator.Acceptable
        else:
            match = re.match(self.__regexp, inputString)
            if match and len(match.group(0)) == len(inputString):
                return QValidator.Intermediate
        return QValidator.Invalid
