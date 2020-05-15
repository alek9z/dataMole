import logging
from typing import Tuple, List

import networkx as nx
from PySide2.QtCore import QThreadPool, Slot, QObject, Signal

from data_preprocessor import data
from data_preprocessor.flow.OperationDag import OperationDag, OperationNode
from data_preprocessor.status import NodeStatus
from data_preprocessor.threads import NodeWorker


# NOTE: Eventualmente memorizzare con joblib
# from joblib import Memory


class OperationHandler:
    """ Executes a DAG """

    def __init__(self, graph: OperationDag):
        self.graph: nx.DiGraph = graph.getNxGraph()
        self.threadPool = QThreadPool()
        self.__qtSlots = _HandlerSlots(self)
        self.signals = HandlerSignals()

        # self.__memoryContext = Memory(cachedir='/tmp', verbose=1)

    def execute(self):
        """
        Executes the dag flow. This method will emit signals in 'HandlerSignals'

        :raise HandlerException if the flow is not ready to start
        """
        # Find input nodes
        start_nodes_id = [n for (n, deg) in self.graph.in_degree() if deg == 0]
        input_nodes = [node for node in map(lambda nid: self.graph.nodes[nid]['op'], start_nodes_id) if
                       node.operation.maxInputNumber() == 0]
        self._canExecute(input_nodes)

        for node_id in start_nodes_id:
            node: OperationNode = self.graph.nodes[node_id]['op']
            self.startNode(node)

        end = self.threadPool.waitForDone()
        if end:
            logging.debug('ThreadPool ended')
            # Everything finished
            self.signals.allFinished.emit()
            logging.info('Flow finished')

    def startNode(self, node: OperationNode):
        worker = NodeWorker(node)
        # Connect
        worker.signals.result.connect(self.__qtSlots.nodeCompleted)
        worker.signals.error.connect(self.__qtSlots.nodeErrored)
        self.threadPool.start(worker)
        self.signals.statusChanged.emit(node.uid, NodeStatus.PROGRESS)

    def _canExecute(self, input_nodes: List[OperationNode]) -> bool:
        """
        Check if there are input nodes and if options are set

        :raise HandlerException if the flow is not ready for execution
        """
        if not input_nodes:
            logging.error('Flow not started: there are no input operations')
            raise HandlerException('There are no input nodes')
        # Find the set of reachable nodes from the input operations
        reachable = set()
        for node in input_nodes:
            reachable = reachable.union(nx.dag.descendants(self.graph, node.uid))
        # Check if all reachable nodes have options set
        for node_id in reachable:
            node: OperationNode = self.graph.nodes[node_id]['op']
            if not node.operation.hasOptions():
                logging.error('Flow not started: operation {}-{} has options to set'.format(
                    node.operation.name(), node.uid))
                raise HandlerException('Operation {} has options to set'.format(node.operation.name()))
        return True


class HandlerSignals(QObject):
    """
    Graph handler Qt signals.

    - statusChnaged(int, status): operation status changed with new status
    - allFinished: flow execution finished (either because of error or completion)
    """
    statusChanged = Signal(int, NodeStatus)
    allFinished = Signal()


class _HandlerSlots(QObject):
    def __init__(self, handler: OperationHandler, parent: QObject = None):
        super().__init__(parent)
        self.handler = handler

    @Slot(int, object)
    def nodeCompleted(self, node_id: int, result: data.Frame):
        logging.debug('nodeCompleted SUCCESS')
        # Emit node finished
        self.handler.signals.statusChanged.emit(node_id, NodeStatus.SUCCESS)
        # Clear eventual input, since now I have result
        node = self.handler.graph.nodes[node_id]['op']
        node.clearInputArgument()
        # Put result in all child nodes
        for child_id in self.handler.graph.successors(node_id):
            child: OperationNode = self.handler.graph.nodes[child_id]['op']
            child.addInputArgument(result, op_id=node_id)
            # Check if child has all it needs to start
            if self.handler.graph.in_degree(child_id) == child.nInputs:
                # If so, add the worker to thread pool
                self.handler.startNode(child)

    @Slot(int, tuple)
    def nodeErrored(self, node_id: int, error: Tuple[type, Exception, str]):
        msg = str(error[1])
        node = self.handler.graph.nodes[node_id]['op']
        node.clearInputArgument()
        logging.error('Operation {} failed with exception {}: {} - trace: {}'.format(
            node.operation.name(), str(error[0]), msg, error[2]))
        self.handler.signals.statusChanged.emit(node_id, NodeStatus.ERROR)
        # Stop all threads
        self.handler.threadPool.clear()


class HandlerException(Exception):
    def __init__(self, msg: str):
        super().__init__(msg)
