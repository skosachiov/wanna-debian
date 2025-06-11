class Node:
    def __init__(self, name):
        self.name = name
        self.index = -1  # Will be set during sorting
        self.edges = []   # Will store other Node objects

class StableTopoSort:
    @staticmethod
    def stable_topo_sort(nodes):
        # 0. Remember where each node was
        for i in range(len(nodes)):
            nodes[i].index = i

        # 1. Sort edges according to node indices
        for node in nodes:
            node.edges.sort(key=lambda x: x.index)

        # 2. Perform Tarjan SCC
        scc = StableTopoSort.PeaSCC(nodes)
        scc.visit()
        import logging
        logging.debug(f'Tarjan SCC cycles: {StableTopoSort.extract_cycles(nodes, scc.rindex)}')

        # 3. Perform *reverse* counting sort
        StableTopoSort.reverse_counting_sort(nodes, scc.rindex)

        # 4. Compute levels for each node
        levels = [0] * len(nodes)
        for node in nodes:
            for edge in node.edges:
                neighbor = edge.index
                if levels[neighbor] < levels[node.index] + 1:
                    levels[neighbor] = levels[node.index] + 1

        # 5. Pair each node with its level and return as list of tuples
        return [(levels[node.index], node) for node in nodes]

    class PeaSCC:
        def __init__(self, g):
            self.graph = g
            self.rindex = [0] * len(g)
            self.index = 1
            self.c = len(g) - 1

            self.vS = StableTopoSort.DoubleStack(len(g))
            self.iS = StableTopoSort.DoubleStack(len(g))
            self.root = [False] * len(g)

        def visit(self):
            # Attn! We're walking nodes in reverse
            for i in range(len(self.graph) - 1, -1, -1):
                if self.rindex[i] == 0:
                    self.visit_node(i)

        def visit_node(self, v):
            self.begin_visiting(v)

            while not self.vS.is_empty_front():
                self.visit_loop()

        def visit_loop(self):
            v = self.vS.top_front()
            i = self.iS.top_front()

            num_edges = len(self.graph[v].edges)

            # Continue traversing out-edges until none left.
            while i <= num_edges:
                # Continuation
                if i > 0:
                    # Update status for previously traversed out-edge
                    self.finish_edge(v, i - 1)
                if i < num_edges and self.begin_edge(v, i):
                    return
                i += 1

            # Finished traversing out edges, update component info
            self.finish_visiting(v)

        def begin_visiting(self, v):
            # First time this node encountered
            self.vS.push_front(v)
            self.iS.push_front(0)
            self.root[v] = True
            self.rindex[v] = self.index
            self.index += 1

        def finish_visiting(self, v):
            # Take this vertex off the call stack
            self.vS.pop_front()
            self.iS.pop_front()
            # Update component information
            if self.root[v]:
                self.index -= 1
                while not self.vS.is_empty_back() and self.rindex[v] <= self.rindex[self.vS.top_back()]:
                    w = self.vS.pop_back()
                    self.rindex[w] = self.c
                    self.index -= 1
                self.rindex[v] = self.c
                self.c -= 1
            else:
                self.vS.push_back(v)

        def begin_edge(self, v, k):
            w = self.graph[v].edges[k].index

            if self.rindex[w] == 0:
                self.iS.pop_front()
                self.iS.push_front(k + 1)
                self.begin_visiting(w)
                return True
            else:
                return False

        def finish_edge(self, v, k):
            w = self.graph[v].edges[k].index

            if self.rindex[w] < self.rindex[v]:
                self.rindex[v] = self.rindex[w]
                self.root[v] = False

    @staticmethod
    def reverse_counting_sort(nodes, rindex):
        count = [0] * len(nodes)

        for i in range(len(rindex)):
            cindex = len(nodes) - 1 - rindex[i]
            count[cindex] += 1

        for i in range(1, len(count)):
            count[i] += count[i - 1]

        output = [None] * len(nodes)
        for i in range(len(output)):
            cindex = len(nodes) - 1 - rindex[i]

            # Attn! We're sorting in reverse
            output_index = len(output) - count[cindex]

            output[output_index] = nodes[i]
            count[cindex] -= 1

        nodes[:] = output[:]

    @staticmethod
    def extract_cycles(nodes, rindex):
        # Group nodes by their component index
        components = {}
        for i, node in enumerate(nodes):
            comp = rindex[i]
            if comp not in components:
                components[comp] = []
            components[comp].append(node)
        
        # Filter components with more than one node (these contain cycles)
        cycles = [comp for comp in components.values() if len(comp) > 1]
        
        return {
            'cycle_count': len(cycles),
            'cycles': cycles
        }

    class DoubleStack:
        def __init__(self, capacity):
            self.items = [0] * capacity
            self.fp = 0  # front pointer
            self.bp = capacity  # back pointer

        def is_empty_front(self):
            return self.fp == 0

        def top_front(self):
            return self.items[self.fp - 1]

        def pop_front(self):
            self.fp -= 1
            return self.items[self.fp]

        def push_front(self, item):
            self.items[self.fp] = item
            self.fp += 1

        def is_empty_back(self):
            return self.bp == len(self.items)

        def top_back(self):
            return self.items[self.bp]

        def pop_back(self):
            val = self.items[self.bp]
            self.bp += 1
            return val

        def push_back(self, item):
            self.bp -= 1
            self.items[self.bp] = item
