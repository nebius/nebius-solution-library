#!/bin/bash

# Script to convert "nebius compute gpu-cluster get --id <gpu-cluster-id> --format yaml" 
# to SLURM tree topology.conf format https://slurm.schedmd.com/topology.conf.html#SECTION_topology/tree
# Usage: 
# nebius compute gpu-cluster get --id <gpu-cluster-id> --format yaml | ./create_slurm_topology.sh > topology.conf


input_file="$1"

# Handle stdin input or file input
if [ -z "$input_file" ] || [ "$input_file" = "-" ]; then
    # Read from stdin
    input_file="/dev/stdin"
elif [ ! -f "$input_file" ]; then
    echo "Usage: $0 <input_file|-> or pipe input"
    echo "Examples:"
    echo "  $0 input.yaml > topology.conf"
    echo "  $0 - < input.yaml > topology.conf"
    echo "  cat input.yaml | $0 - > topology.conf"
    echo "  ./create_slurm_topology.sh | $0 - > topology.conf"
    exit 1
fi

# Temporary files for processing
temp_instances="/tmp/instances_$$"
temp_level1="/tmp/level1_$$"
temp_level2="/tmp/level2_$$"
temp_level3="/tmp/level3_$$"

# Clean up temporary files on exit
trap 'rm -f "$temp_instances" "$temp_level1" "$temp_level2" "$temp_level3"' EXIT

# Parse the YAML file to extract instance topology information
awk '
BEGIN { 
    in_topology = 0
    in_instances = 0
    current_instance = ""
    in_path = 0
    path_level = 0
}

# Look for infiniband_topology_path section
/infiniband_topology_path:/ {
    in_topology = 1
    next
}

# Look for instances subsection within topology
in_topology && /^[[:space:]]+instances:/ {
    in_instances = 1
    next
}

# Stop when we hit the general instances section (not indented under infiniband_topology_path)
in_topology && /^[[:space:]]*instances:/ && !/^[[:space:]]+instances:/ {
    in_topology = 0
    in_instances = 0
}

# Parse instance_id
in_instances && /instance_id:/ {
    gsub(/.*instance_id:[[:space:]]*/, "")
    current_instance = $0
    in_path = 0
    path_level = 0
    level1 = ""
    level2 = ""
    level3 = ""
    next
}

# Look for path section
in_instances && /path:/ {
    in_path = 1
    path_level = 0
    next
}

# Parse path elements
in_path && /^[[:space:]]*-/ {
    gsub(/^[[:space:]]*-[[:space:]]*/, "")
    gsub(/"/, "")
    path_level++
    
    if (path_level == 1) level1 = $0
    else if (path_level == 2) level2 = $0
    else if (path_level == 3) {
        level3 = $0
        # Output the complete instance record
        if (current_instance != "" && level1 != "" && level2 != "" && level3 != "") {
            print current_instance "|" level1 "|" level2 "|" level3
        }
        in_path = 0
    }
    next
}

# Reset when we encounter a new instance (starts with "- instance_id")
in_instances && /^[[:space:]]*- instance_id:/ {
    in_path = 0
}

' "$input_file" > "$temp_instances"

# Check if we have any instances
if [ ! -s "$temp_instances" ]; then
    echo "Error: No valid instance topology data found in input file" >&2
    echo "Debug: Contents of temp file:" >&2
    cat "$temp_instances" >&2
    echo "Debug: Searching for infiniband_topology_path:" >&2
    grep -n "infiniband_topology_path" "$input_file" >&2
    exit 1
fi

# Process each instance and build switch relationships
while IFS='|' read -r instance level1 level2 level3; do
    # Store level1 -> level2 relationships
    echo "$level1|$level2" >> "$temp_level1"
    
    # Store level2 -> level3 relationships  
    echo "$level2|$level3" >> "$temp_level2"
    
    # Store level3 -> instance relationships
    echo "$level3|$instance" >> "$temp_level3"
done < "$temp_instances"

# Function to get unique switches for a parent
get_switches() {
    local parent="$1"
    local file="$2"
    grep "^$parent|" "$file" 2>/dev/null | cut -d'|' -f2 | sort -u | tr '\n' ',' | sed 's/,$//'
}

# Function to get nodes for a switch
get_nodes() {
    local switch="$1"
    local file="$2"
    grep "^$switch|" "$file" 2>/dev/null | cut -d'|' -f2 | sort -u | tr '\n' ',' | sed 's/,$//'
}

# Generate SLURM topology configuration
echo "# Switch configuration"

# Get all unique level1 switches
if [ -s "$temp_level1" ]; then
    level1_switches=$(cut -d'|' -f1 "$temp_level1" | sort -u)
    
    # Level 1 switches (top level)
    for level1 in $level1_switches; do
        children=$(get_switches "$level1" "$temp_level1")
        if [ -n "$children" ]; then
            echo "SwitchName=$level1 Switches=$children"
        fi
    done
fi

# Get all unique level2 switches
if [ -s "$temp_level2" ]; then
    level2_switches=$(cut -d'|' -f1 "$temp_level2" | sort -u)
    
    # Level 2 switches (middle level)
    for level2 in $level2_switches; do
        children=$(get_switches "$level2" "$temp_level2")
        if [ -n "$children" ]; then
            echo "SwitchName=$level2 Switches=$children"
        fi
    done
fi

# Get all unique level3 switches
if [ -s "$temp_level3" ]; then
    level3_switches=$(cut -d'|' -f1 "$temp_level3" | sort -u)
    
    # Level 3 switches (leaf level) - these connect to nodes
    for level3 in $level3_switches; do
        nodes=$(get_nodes "$level3" "$temp_level3")
        if [ -n "$nodes" ]; then
            echo "SwitchName=$level3 Nodes=$nodes"
        fi
    done
fi