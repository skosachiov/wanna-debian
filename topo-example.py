from toposort import *
import random

# Example graph represented as a dictionary of sets
graph_dict = {
    "main": {"a4", "a1", "b2"},
    "a2": {"a1"},
    "a1": set(),
    "b2": {"b1", "a2"},
    "b1": set(),
    "a3": {"b2", "b1"},
    "a4": {"a3"}
}

def generate_random_graph(num_nodes=10000, max_out_edges=100):
    graph = {}
    for i in range(num_nodes):
        # Determine number of outgoing edges (random between 0 and max_out_edges)
        num_edges = random.randint(0, max_out_edges)
        # Generate random edges (targets are 0 to edge_value_range-1)
        edges = set()
        for _ in range(num_edges):
            edge_target = random.randint(0, num_nodes - 1)
            edges.add(f"node_{edge_target}")
        graph[f"node_{i}"] = edges
    return graph

# graph_dict = generate_random_graph(10000, 100)
print(graph_dict)

# Convert the dictionary of sets to a list of Node objects
def create_node_list(graph_dict):
    # First create all nodes
    nodes = {name: Node(name) for name in graph_dict}
    
    # Then set up the edges
    for name, edges in graph_dict.items():
        node = nodes[name]
        for edge_name in edges:
            node.edges.append(nodes[edge_name])
    
    return list(nodes.values())

# Create the node list from our graph
nodes = create_node_list(graph_dict)

# Perform stable topological sort
sorted_nodes_with_levels = StableTopoSort.stable_topo_sort(nodes)
print("Sorted Nodes with Levels:")
for level, node in sorted_nodes_with_levels:
    print(f"Level {level}: Node {node.name}")
