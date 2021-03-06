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
from typing import Dict

import pandas as pd

from ..interface.operation import Operation
from ... import data
from ...data.types import Types, Type


class AttributeStatistics(Operation):
    def __init__(self):
        super().__init__()
        self.__attribute: int = -1

    def execute(self, df: data.Frame) -> Dict[str, object]:
        desc: Dict[str, object] = df.getRawFrame().iloc[:, self.__attribute].describe().to_dict()
        # Rename centiles
        centiles = [(k, v) for k, v in desc.items() if re.fullmatch('.*%', k)]
        for k, v in centiles:
            desc['Centile ' + k] = desc.pop(k)
        # Rename Top and Freq
        if desc.get('top', None) is not None and desc.get('freq', None) is not None:
            desc['Most frequent'] = '{} (n={})'.format(desc.pop('top'), desc.pop('freq'))
        # Add Nan count
        nan_count = df.nRows - int(desc['count'])
        del desc['count']
        desc['Nan count'] = '{:d} ({:.2f}%)'.format(nan_count, nan_count / df.nRows * 100)
        if desc.get('mean', None) is not None and desc.get('std', None) is not None:
            desc['Mean'] = '{:.3f}'.format(desc.pop('mean'))
            desc['Std'] = '{:.3f}'.format(desc.pop('std'))
        # Uppercase letter
        desc = dict(map(lambda t: (t[0][0].upper() + t[0][1:], t[1]), desc.items()))
        return desc

    def setOptions(self, attribute: int) -> None:
        self.__attribute: int = attribute


class Hist(Operation):
    def __init__(self):
        super().__init__()
        self.__attribute: int = None
        self.__type: Types = None
        self.__nBins: int = None

    def execute(self, df: data.Frame) -> Dict[object, int]:
        col = df.getRawFrame().iloc[:, self.__attribute]
        if self.__type == Types.Numeric or self.__type == Types.Datetime:
            # Differently from value_counts, this handles the case where all values are nan
            cuts = pd.cut(col, bins=self.__nBins, duplicates='drop')
            values = cuts.value_counts(sort=False)
            if self.__type == Types.Numeric:
                values.index = values.index.map(lambda i: '{:.2f}'.format(i.left))
            else:
                # Datetime
                fmt = '%Y-%m-%d %H:%M'
                values.index = values.index.map(lambda i: i.left.strftime(fmt))
            return values.to_dict()
        else:
            return col.value_counts(sort=False).to_dict()

    def setOptions(self, attribute: int, attType: Type, bins: int = None) -> None:
        self.__attribute = attribute
        self.__type = attType
        self.__nBins = bins if bins else None
