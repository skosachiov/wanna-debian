import pytest
from toposort import *
from predose import reverse_graph
import random

# Example graph represented as a dictionary of sets
graph_dict = {
    "ubuntu-desktop": {"gnome-shell", "nautilus", "firefox", "libreoffice", "systemd"},
    "gnome-shell": {"gdm3", "gnome-session", "libglib2.0-0"},
    "gdm3": {"systemd", "libpam0g", "xorg"},
    "gnome-session": {"gnome-shell", "gsettings-desktop-schemas"},
    "nautilus": {"libgtk-3-0", "libglib2.0-0", "gvfs"},
    "firefox": {"libgtk-3-0", "libc6", "libstdc++6"},
    "libreoffice": {"libreoffice-core", "libreoffice-writer", "java-runtime"},
    "libreoffice-core": {"libc6", "libstdc++6", "python3"},
    "libreoffice-writer": {"libreoffice-core"},
    "java-runtime": {"java-common", "libc6"},
    "systemd": {"libc6", "libpam0g", "dbus"},
    "xorg": {"xserver-xorg", "libdrm2", "libgl1"},
    "xserver-xorg": {"libc6", "libpam0g", "libdrm2"},
    "libgtk-3-0": {"libglib2.0-0", "libpango-1.0-0", "libcairo2"},
    "libglib2.0-0": {"libc6", "libpcre3"},
    "gsettings-desktop-schemas": {"libglib2.0-0"},
    "gvfs": {"libglib2.0-0", "libsecret-1-0"},
    "libsecret-1-0": {"libglib2.0-0", "libgcrypt20"},
    "libpam0g": {"libc6"},
    "dbus": {"libc6", "libsystemd0"},
    "libdrm2": set(),
    "libgl1": {"libc6", "libdrm2"},
    "libpango-1.0-0": {"libglib2.0-0", "libcairo2", "libharfbuzz0b"},
    "libcairo2": {"libc6", "libfontconfig1", "libfreetype6"},
    "libpcre3": {"libc6"},
    "libgcrypt20": {"libc6", "libgpg-error0"},
    "libsystemd0": {"libc6"},
    "libharfbuzz0b": {"libc6", "libglib2.0-0"},
    "libfontconfig1": {"libc6", "libexpat1"},
    "libfreetype6": {"libc6", "libpng16-16"},
    "libgpg-error0": {"libc6"},
    "libexpat1": {"libc6"},
    "libpng16-16": {"libc6"},
    "python3": {"libc6", "libpython3.9"},
    "libpython3.9": {"libc6"},
    "java-common": {"libc6"},
    "libc6": set(),
    "libstdc++6": {"libc6", "libgcc-s1"},
    "libgcc-s1": {"libc6"}
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
# print(graph_dict)

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

def test_toposort():
    # Create the node list from our graph
    r_graph = reverse_graph(graph_dict)
    nodes = create_node_list(r_graph)

    expected = [
        (0, 'libc6'),
        (0, 'libdrm2'),
        (1, 'java-common'),
        (1, 'libexpat1'),
        (1, 'libgcc-s1'),
        (1, 'libgl1'),
        (1, 'libgpg-error0'),
        (1, 'libpam0g'),
        (1, 'libpcre3'),
        (1, 'libpng16-16'),
        (1, 'libpython3.9'),
        (1, 'libsystemd0'),
        (2, 'dbus'),
        (2, 'java-runtime'),
        (2, 'libfontconfig1'),
        (2, 'libfreetype6'),
        (2, 'libgcrypt20'),
        (2, 'libglib2.0-0'),
        (2, 'libstdc++6'),
        (2, 'python3'),
        (2, 'xserver-xorg'),
        (3, 'gsettings-desktop-schemas'),
        (3, 'libcairo2'),
        (3, 'libharfbuzz0b'),
        (3, 'libreoffice-core'),
        (3, 'libsecret-1-0'),
        (3, 'systemd'),
        (3, 'xorg'),
        (4, 'gdm3'),
        (4, 'gvfs'),
        (4, 'libpango-1.0-0'),
        (4, 'libreoffice-writer'),
        (5, 'libgtk-3-0'),
        (5, 'libreoffice'),
        (6, 'firefox'),
        (6, 'gnome-session'),
        (6, 'nautilus'),
        (7, 'gnome-shell'),
        (7, 'ubuntu-desktop')
    ]

    # Perform stable topological sort
    sorted_nodes_with_levels = StableTopoSort.stable_topo_sort(nodes)
    # print("Sorted Nodes with Levels:")
    tl = []
    for level, node in sorted_nodes_with_levels:
        tl.append((level, node.name))
    for s, e in zip(sorted(tl), expected):
        assert s == e
        # print(f"Level {level}: Node {node.name}")
