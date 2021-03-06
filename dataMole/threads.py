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

import sys
import traceback
from typing import Tuple, Any, Union

from PySide2.QtCore import QRunnable, Slot, QObject, Signal

from dataMole import flogging


class Worker(QRunnable):
    """
    Build a runnable object to execute an operation in a new thread
    """

    class WorkerSignals(QObject):
        """
        Wraps Worker signals used to communicate with other Qt widgets.

        - finished(id): signal emitted when no the worker is closed
        - error(id, tuple): emitted when worker caught an exception. It includes 3 values: the exception type, the exception object and the stacktrace as string
        - result(id, Frame): emitted when the worker exited successfully and carries the result of the computation

        """
        finished = Signal(object)
        error = Signal(object, tuple)
        result = Signal(object, object)

    def __init__(self, executable: Union['Operation', 'OperationNode'], args: Tuple = tuple(),
                 identifier: Any = None):
        """
        Builds a worker to run an operation

        :param executable: an object with an 'execute' function which returns a data.Frame
        :param args: arguments to pass to 'execute' function (omit them if there are none)
        :param identifier: object to emit as first argument of every signal
        """
        super().__init__()
        self._executable = executable
        self._args = args
        self._identifier = identifier
        self.signals = Worker.WorkerSignals()
        self.setAutoDelete(True)

    # noinspection PyBroadException
    @Slot()
    def run(self) -> None:
        """ Reimplements QRunnable method to run the executable """
        try:
            result = self._executable.execute(*self._args)
        except Exception:
            flogging.appLogger.debug('Worker got exception: id={}'.format(self._identifier))
            trace: str = traceback.format_exc()
            flogging.appLogger.error(trace)
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit(self._identifier, (exctype, value, trace))
        else:
            flogging.appLogger.debug('Worker emits result: id={}'.format(self._identifier))
            self.signals.result.emit(self._identifier, result)
        finally:
            flogging.appLogger.debug('Worker finished: id={}'.format(self._identifier))
            self.signals.finished.emit(self._identifier)
